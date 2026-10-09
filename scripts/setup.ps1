[CmdletBinding()]
param([switch]$WithBridge)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
    }
    $py = Join-Path $root '.venv/Scripts/python.exe'
    & $py -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    New-Item -ItemType Directory -Path data/inbox -Force | Out-Null
    if ($WithBridge) {
        & $py -m pip install -r requirements-bridge.txt
        if ($LASTEXITCODE -ne 0) { throw 'Optional bridge installation failed.' }
        $revision = 'ae70f5e6e167474e93d4c2beeb8ae3d3297d5ade'
        if (-not (Test-Path -LiteralPath 'work/upstream')) {
            New-Item -ItemType Directory -Path work -Force | Out-Null
            git clone https://github.com/shkyyy18/mi_fitness_data_bridge.git work/upstream
            if ($LASTEXITCODE -ne 0) { throw 'Bridge example checkout failed.' }
            git -C work/upstream checkout --detach $revision
            if ($LASTEXITCODE -ne 0) { throw 'Bridge revision checkout failed.' }
        }
        $actual = git -C work/upstream rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $actual -ne $revision) {
            throw 'Existing upstream checkout differs from evaluated revision; inspect it manually.'
        }
    }
    Write-Host 'Ready. No account setup or cloud login performed.'
} finally { Pop-Location }
