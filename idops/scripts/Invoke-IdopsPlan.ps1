<#
.SYNOPSIS
  Lab-only joiner/mover/leaver plan. Does not call Graph or Active Directory.

.DESCRIPTION
  Wraps `python -m idops plan` so the same CSV and directory fixture can be
  demoed from PowerShell. If you want the native CLI, use `idops plan` after
  `pip install -e .`.
#>
param(
    [Parameter(Mandatory = $true)]
    [string] $Csv,

    [Parameter(Mandatory = $true)]
    [string] $Directory,

    [ValidateSet("text", "json")]
    [string] $Format = "text"
)

$ErrorActionPreference = "Stop"
python -m idops plan -c $Csv -d $Directory --format $Format
exit $LASTEXITCODE
