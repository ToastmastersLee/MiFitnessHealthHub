$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $py = Join-Path $root '.venv/Scripts/python.exe'
    & $py -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $py -m ruff check src tests scripts
    if ($LASTEXITCODE -ne 0) { throw 'Code checks failed.' }
    & $py -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency checks failed.' }
} finally { Pop-Location }
