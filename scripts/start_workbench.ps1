param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run first_run.bat first.' }
$argsList = @((Join-Path $PSScriptRoot 'workbench_service.py'))
if ($NoBrowser) { $argsList += '--no-browser' }
& $python @argsList
if ($LASTEXITCODE -ne 0) { throw 'Workbench startup failed. Logs were preserved.' }
