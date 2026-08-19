# nethealth

Lab-safe ICMP, TCP, DNS, HTTP, and TLS checks with text, JSON, and HTML reports.

Use this against hosts and services **you operate**. It is a monitoring helper, not a scanner.

## Why

A systems or network engineer needs a repeatable way to answer “is this service up, and is the certificate still valid?” before a change window, and a report that can go in a ticket. 

`nethealth` is a single CLI that does that from a TOML/JSON suite or one-off flags.

## Install

```bash
cd nethealth
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick start

```bash
nethealth check --icmp 127.0.0.1 --dns localhost
nethealth check -c examples/lab.toml
nethealth check -c examples/lab.toml --format json
nethealth check -c examples/lab.toml --format html -o report.html
```

Requires Python 3.11 or newer (it uses the standard library `tomllib`).

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | all checks passed (skips allowed) |
| `1` | one or more checks failed or errored |
| `2` | usage or config error |
| `130` | interrupted, or the output pipe closed early |

The exit code is the point: drop `nethealth check -c prod.toml` into cron, a pipeline, or a change-window script and let it gate the next step.

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

JSON suites are also accepted. Check types: `icmp`, `tcp`, `dns` (`A` or `AAAA`, optional `expect` address list), `http`, `tls`.

Every check needs a unique `name`, because the name is what identifies the row in the report.

## Sample text report

```
nethealth  cli  2026-08-19T06:08:37Z

PASS   icmp-1  icmp  127.0.0.1       0.1ms  echo reply received
FAIL   tcp-1   tcp   127.0.0.1:9     7.9ms  [Errno 61] Connection refused
PASS   dns-1   dns   localhost A     8.1ms  127.0.0.1

FAILED  2 pass, 1 fail  (8.6ms)
```

The JSON report carries the same data plus per-check `details` (resolved addresses, HTTP status, certificate expiry), so it can be shipped to a log collector or diffed between runs.

## Architecture

```
CLI (argparse) → suite TOML/JSON or flags
               → runner (optional thread pool)
               → probes (stdlib only: ping, socket, urllib, ssl)
               → text | JSON | HTML report
```

No runtime dependencies. ICMP uses the system `ping` binary and is skipped if it is not on `PATH`. Checks run concurrently by default, so a suite of slow-timeout targets finishes in about the time of the slowest one rather than the sum. Tests mock the network; they do not probe the public internet.

## Known limits

Worth knowing before you trust a result:

- **DNS timeouts are not enforced.** `socket.getaddrinfo` has no timeout parameter, so a wedged resolver can block a DNS check past `timeout_seconds`. The check is accurate, it is just not bounded.
- **HTTP follows redirects.** `expect_status` is matched against the final response, so a `301` to a healthy page reads as `200`.
- **TLS checks verify the chain.** An untrusted or self-signed certificate fails before expiry is ever read. That is deliberate, but it means an internal CA has to be in the trust store for the expiry warning to be useful.
- **ICMP depends on the system `ping`.** Flag syntax differs per platform and is handled for macOS, Linux, and Windows. Anything else may report a parse-level failure rather than a network one.

## Troubleshooting

**Every HTTPS and TLS check fails with `CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate`.** The Python install has no CA trust store rather than the servers being broken. `nethealth` detects this and says so in the message. On a python.org macOS build, run the bundled installer once:

```bash
"/Applications/Python 3.12/Install Certificates.command"
```

Otherwise, point `SSL_CERT_FILE` at a CA bundle.

## Tests

```bash
pytest
```

63 tests, no network access required. They cover config validation and its rejection paths, each probe type via mocks, report rendering and HTML escaping, and CLI exit codes.
