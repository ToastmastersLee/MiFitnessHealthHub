[CmdletBinding()]
param(
    [ValidateSet('Local', 'Cloud')][string]$Mode = 'Local',
    [string]$StartDate,
    [string]$EndDate,
    [string]$Subject = 'band9-local',
    [switch]$EnableCloud
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $py = Join-Path $root '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $py)) { throw 'Run scripts/setup.ps1 first.' }
    if ($Mode -eq 'Cloud') {
        if (-not $EnableCloud) { throw 'Cloud mode requires -EnableCloud after manual account setup.' }
        if (-not $StartDate -or -not $EndDate) { throw 'Cloud mode requires explicit start and end dates.' }
        & $py -c "import sys; from datetime import date; a,b=sys.argv[1:]; assert date.fromisoformat(a).isoformat()==a and date.fromisoformat(b).isoformat()==b and a<=b" $StartDate $EndDate
        if ($LASTEXITCODE -ne 0) { throw 'Invalid date range.' }
        $bridge = Join-Path $root '.venv/Scripts/mi-fitness-bridge.exe'
        if (-not (Test-Path -LiteralPath $bridge)) { throw 'Install the optional bridge first.' }
        New-Item -ItemType Directory -Path data/inbox, work/logs -Force | Out-Null
        # Capture upstream output locally, never echo possible account details to an agent.
        & $bridge sync --db data/bridge.db --start-date $StartDate --end-date $EndDate *> work/logs/bridge-sync.log
        if ($LASTEXITCODE -ne 0) { throw 'Cloud sync failed. Private diagnostics are in work/logs/bridge-sync.log.' }
        & $bridge export --db data/bridge.db --format json --output data/inbox/bridge.json *> work/logs/bridge-export.log
        if ($LASTEXITCODE -ne 0) { throw 'Bridge export failed. Inspect its private local log.' }
    }
    & $py -m healthhub sync --subject $Subject
    if ($LASTEXITCODE -ne 0) { throw 'Local import failed; earlier successful files remain imported.' }
    & $py -m healthhub summary --subject $Subject
    if ($LASTEXITCODE -ne 0) { throw 'Summary failed.' }
} finally { Pop-Location }
