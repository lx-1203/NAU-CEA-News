param([switch]$SkipWorkbench, [switch]$PlanOnly, [switch]$UpdateOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$manifest = Get-Content -LiteralPath (Join-Path $root 'config\reuse-components.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($PlanOnly) {
    Write-Output ('Python: ' + $manifest.python)
    Write-Output ('UV: ' + $manifest.downloads.uv.url)
    Write-Output ('Studio: ' + $manifest.downloads.studio.url)
    Write-Output ('Workbench: ' + $manifest.downloads.patch.url)
    Write-Output ('Model files: ' + $manifest.models.Count)
    return
}
$taskConfigPath = Join-Path $root 'config\pipeline.json'
if (-not (Test-Path -LiteralPath $taskConfigPath)) {
    Copy-Item -LiteralPath (Join-Path $root 'config\pipeline.example.json') -Destination $taskConfigPath
}
$initialConfig = Get-Content -LiteralPath $taskConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $UpdateOnly -and -not $initialConfig.portable_profile) { throw 'Use the exported reuse bundle for clean setup. The current production configuration was preserved.' }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $root 'runtime\python'
$env:UV_CACHE_DIR = Join-Path $root 'runtime\cache\uv'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $root 'runtime\browsers'
$env:PATH = (Join-Path $root '.tools\gh\bin') + ';' + $env:PATH
$tools = Join-Path $root '.tools'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$uvFolder = Join-Path $tools 'uv'
$uv = Join-Path $uvFolder 'uv.exe'
if (-not (Test-Path -LiteralPath $uv)) {
    $zip = Join-Path $tools 'uv.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $manifest.downloads.uv.url -OutFile $zip
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.downloads.uv.sha256) { throw 'UV download SHA256 mismatch.' }
    Expand-Archive -LiteralPath $zip -DestinationPath $uvFolder -Force
}
if ((-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\vcruntime140.dll'))) -or (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\vcruntime140_1.dll')))) {
    $vc = Join-Path $tools 'vc_redist.x64.exe'
    Invoke-WebRequest -UseBasicParsing -Uri $manifest.links.vc_runtime -OutFile $vc
    $signature = Get-AuthenticodeSignature -LiteralPath $vc
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft*') { throw 'Microsoft runtime signature check failed.' }
    $vcProcess = Start-Process -FilePath $vc -ArgumentList @('/install','/passive','/norestart') -WindowStyle Hidden -Wait -PassThru
    if ($vcProcess.ExitCode -notin @(0,1638,3010)) { throw 'Microsoft runtime installation failed.' }
}
& $uv python install 3.11
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & $uv venv --python 3.11 (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
$taskUpdateJson = & $python -X utf8 -B (Join-Path $root 'scripts\check_updates.py') --apply
if ($LASTEXITCODE -ne 0) { throw 'Architecture/skill update check failed. Existing files were preserved.' }
$taskUpdateReceipt = $taskUpdateJson | ConvertFrom-Json
if ($taskUpdateReceipt.rerun_required) {
    $taskRestartArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath)
    if ($SkipWorkbench) { $taskRestartArgs += '-SkipWorkbench' }
    if ($UpdateOnly) { $taskRestartArgs += '-UpdateOnly' }
    & powershell.exe @taskRestartArgs
    if ($LASTEXITCODE -ne 0) { throw 'Updated bootstrap failed in its fresh process.' }
    return
}
if ($UpdateOnly) { Write-Output $taskUpdateJson; return }
if (-not (Test-Path -LiteralPath (Join-Path $root 'assets\qualified-assets.json'))) {
    throw 'Shared production assets are missing. Clone the project repository with the assets directory before full setup. See docs/REUSE_GUIDE.md.'
}
& $python (Join-Path $root 'scripts\verify_assets.py')
if ($LASTEXITCODE -ne 0) { throw 'Shared asset verification failed. Check the repository checkout before installing models.' }
& $uv pip install --python $python -r (Join-Path $root 'pipeline\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'News dependency installation failed.' }
& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed.' }
& $python -c "import sys;sys.path.insert(0,'scripts');from install_workbench import download,extract_safe;import json;from pathlib import Path;d=json.loads(Path('config/reuse-components.json').read_text('utf8'))['downloads']['gh'];p=download(d['url'],Path('.tools/gh.zip'),d['sha256']);extract_safe(p,Path('.tools/gh'))"
if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI setup failed.' }
$config = Get-Content -LiteralPath (Join-Path $root 'config\pipeline.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($config.portable_profile) { & $python -m pipeline.portable configure; if ($LASTEXITCODE -ne 0) { throw 'Portable configuration failed.' } }
if (-not $SkipWorkbench) {
    & $python (Join-Path $PSScriptRoot 'install_workbench.py') --uv $uv
    if ($LASTEXITCODE -ne 0) { throw 'Workbench installation failed. Partial downloads were kept.' }
    & $python (Join-Path $PSScriptRoot 'smoke_voices.py')
    if ($LASTEXITCODE -ne 0) { throw 'Two-voice smoke test failed. Read outputs/setup-smoke before production.' }
}
$desktop = [Environment]::GetFolderPath('Desktop')
New-Item -ItemType Directory -Path (Join-Path $root 'runtime') -Force | Out-Null
'{"setup":"ready"}' | Set-Content -LiteralPath (Join-Path $root 'runtime\setup-ready.json') -Encoding UTF8
$shortcutPath = Join-Path $desktop 'NAU CEA News.lnk'
if (-not (Test-Path -LiteralPath $shortcutPath)) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $root 'start.bat'
    $shortcut.WorkingDirectory = $root
    $shortcut.Save()
}
Write-Output 'SETUP READY. Run start.bat. Complete the two-voice listening check before producing an episode.'
