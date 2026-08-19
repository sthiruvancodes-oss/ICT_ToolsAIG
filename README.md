# ICT Tools

Public lab tools for **IT systems and network administration**: monitoring, addressing, configuration drift, host baselines, and log triage.

These are operator tools for networks and hosts you administer. They are not scanners or exploit tooling.

Each tool is a self-contained Python package with its own README, tests, and CLI. The house rules are the same across all of them: standard library where practical, useful exit codes so the tool can gate a script, machine-readable output as well as human-readable, and a clear statement of what the tool does not check.

## Tools

| Tool | Status | What it does |
| --- | --- | --- |
| [nethealth](nethealth/) | Ready | ICMP / TCP / DNS / HTTP / TLS checks with text, JSON, and HTML reports |

Next: IPAM / VLSM planner, config drift, Linux host audit, log triage, inventory from a supplied host list.

## Lab use only!!!

Point every tool at systems you own or are authorised to operate. Please **DO NOT **use them against third-party networks.
