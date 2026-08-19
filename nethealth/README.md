# nethealth

I got tired of pinging a box, checking a port, looking up DNS, then going to find out when the cert expires, then pasting all of that into a ticket.

`nethealth` does those checks from a TOML or JSON list, or from one-off flags. It prints a table, JSON, or an HTML file. Point it at hosts you actually operate. It is not a scanner.

## Install

Python 3.11 or newer. No extra runtime packages. ICMP shells out to the system `ping`.

```bash
cd nethealth
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows: `.\.venv\Scripts\activate`.

## Run it

```bash
nethealth check --icmp 127.0.0.1 --dns localhost
nethealth check -c examples/lab.toml
nethealth check -c examples/lab.toml --format json
nethealth check -c examples/lab.toml --format html -o report.html
```

`--jobs` controls concurrency (default 8, `1` is sequential). `--timeout` overrides the suite timeout.

Exit codes matter. Put this in cron or a change script and let it stop you.

| Code | Meaning |
| --- | --- |
| `0` | everything passed (skips are fine) |
| `1` | at least one check failed or errored |
| `2` | bad flags or a broken suite file |
| `130` | Ctrl-C, or the pipe closed |

## Suite file

```toml
name = "lab"
timeout_seconds = 3.0
warn_tls_days = 14

[[checks]]
name = "loopback-ping"
type = "icmp"
host = "127.0.0.1"

[[checks]]
name = "localhost-a"
type = "dns"
query = "localhost"
record = "A"

[[checks]]
name = "local-ssh"
type = "tcp"
host = "127.0.0.1"
port = 22

[[checks]]
name = "intranet-https"
type = "http"
url = "https://intranet.example.invalid/health"
expect_status = 200

[[checks]]
name = "intranet-cert"
type = "tls"
host = "intranet.example.invalid"
port = 443
warn_days = 14
```

JSON works too. Types: `icmp`, `tcp`, `dns` (`A` or `AAAA`, optional `expect` list of addresses), `http`, `tls`.

Names have to be unique. The name is the row in the report.

## What the text report looks like

```
nethealth  cli  2026-08-19T06:08:37Z

PASS   icmp-1  icmp  127.0.0.1       0.1ms  echo reply received
FAIL   tcp-1   tcp   127.0.0.1:9     7.9ms  [Errno 61] Connection refused
PASS   dns-1   dns   localhost A     8.1ms  127.0.0.1

FAILED  2 pass, 1 fail  (8.6ms)
```

JSON has the same rows plus extras: resolved addresses, HTTP status, cert expiry. Handy if you ship it to a log or diff two runs.

## How it is put together

CLI reads a suite file or flags, runs the probes (optionally in a thread pool), then renders the report. ICMP is `ping`. Everything else is the standard library (`socket`, `urllib`, `ssl`). If `ping` is missing, that check is skipped instead of crashing.

Checks run at the same time by default, so a handful of slow timeouts takes about as long as the slowest one.

## Things it will not do

- **DNS timeouts.** `getaddrinfo` has no timeout. If the resolver wedges, that check can sit there past `timeout_seconds`. The answer is still right, it just might be late.
- **HTTP follows redirects.** `expect_status` is the final page. A `301` to a healthy box looks like `200`.
- **TLS verifies the chain.** Self-signed or an internal CA that is not in the trust store fails before expiry is even read. That is on purpose. Put the CA in the store if you care about the expiry warning.
- **ICMP is whatever `ping` your OS shipped.** macOS, Linux and Windows flags are handled. Something else may fail in a confusing way.

## HTTPS and TLS all fail with `CERTIFICATE_VERIFY_FAILED`

Your Python has no CA bundle. The servers are probably fine. On a python.org macOS install, run this once:

```bash
"/Applications/Python 3.12/Install Certificates.command"
```

Or set `SSL_CERT_FILE` to a CA bundle.

## Tests

```bash
pytest
```

63 tests. They mock the network, so they never hit the internet. They cover config validation (including the dumb rejection cases), each probe type, HTML escaping, and the CLI exit codes.
