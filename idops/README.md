# idops

Joiners, movers, and leavers used to arrive as a spreadsheet, then someone clicked through Entra or AD one account at a time.

`idops` reads that CSV and a **lab directory fixture**, then prints a plan: create, move groups, require MFA, or disable. `apply` writes an updated JSON file. It does not call Graph, Entra, or Active Directory. Point it at fixtures you made, not a live tenant.

## Install

Python 3.11 or newer. No extra runtime packages.

```bash
cd idops
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows: `.\.venv\Scripts\activate`.

## Run it

```bash
idops plan -c examples/people.csv -d examples/lab-directory.json
idops plan -c examples/people.csv -d examples/lab-directory.json --format json
idops apply -c examples/people.csv -d examples/lab-directory.json -o /tmp/lab-after.json
```

PowerShell (same plan, still lab-only):

```powershell
./scripts/Invoke-IdopsPlan.ps1 -Csv examples/people.csv -Directory examples/lab-directory.json
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | every row planned cleanly (`apply` also wrote the file) |
| `1` | at least one row is an error (unknown group, person missing, duplicate joiner) |
| `2` | bad flags or a broken CSV / fixture |
| `130` | Ctrl-C, or the pipe closed |

## CSV

Required: `action`, `upn`. Optional: `display_name`, `department`, `title`, `groups`, `mfa_required`.

`action` is `joiner`, `mover`, or `leaver`. Groups are semicolon-separated names that must already exist in the fixture catalog.

```csv
action,upn,display_name,department,title,groups,mfa_required
joiner,alex@lab.example,Alex Chen,Finance,Analyst,All Staff;Finance,true
mover,sam@lab.example,Sam Ortiz,Operations,Supervisor,All Staff;Operations,true
leaver,pat@lab.example,Pat Ng,Warehouse,Picker,,
```

Joiners need a display name and at least one group. Movers that list groups replace membership with that list. Leavers disable the account, strip groups, and add `Disabled Users` when that group exists in the catalog. MFA on a joiner defaults to enforced unless `mfa_required` is false.

## Directory fixture

JSON with a group catalog and current users. `apply` never overwrites the input file; you pass `-o`.

## Tests

```bash
pytest
```
