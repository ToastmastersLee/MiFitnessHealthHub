param(
    [Parameter(Mandatory = $true)][string]$ExportDirectory,
    [string]$Database = 'data/healthhub.db',
    [string]$Subject = 'zepp-life',
    [string]$ReportDirectory = 'private/analysis/zepp-life',
    [switch]$OpenReport
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $interpreter = Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $interpreter -PathType Leaf)) {
        throw 'Run scripts/setup.ps1 first.'
    }
    & $interpreter -m healthhub import-zepp $ExportDirectory --db $Database --subject $Subject
    if ($LASTEXITCODE -ne 0) { throw 'Zepp import failed; report was not regenerated.' }
    & $interpreter -m healthhub zepp-report --db $Database --subject $Subject --output $ReportDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Zepp report failed.' }
    if ($OpenReport) { Invoke-Item -LiteralPath (Join-Path $ReportDirectory 'history.html') }
} finally {
    Pop-Location
}
