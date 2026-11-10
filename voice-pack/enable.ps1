[CmdletBinding()]
param(
    [string]$WorkbenchRoot,
    [switch]$NoLaunch,
    [switch]$NoBrowser,
    [switch]$NonInteractive,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$packRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$utf8 = New-Object Text.UTF8Encoding($false)

function Read-Json([string]$Path) {
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose(); $stream.Dispose() }
}
function Get-SafeChild([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)') {
        throw ('Unsafe relative path: ' + $Relative)
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $path = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (-not $path.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw ('Path escapes target: ' + $Relative)
    }
    $cursor = $path
    while ($cursor -and $cursor.Length -ge $base.Length) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Linked path is not supported: ' + $cursor) }
        }
        if ($cursor -eq $base) { break }
        $cursor = Split-Path -Parent $cursor
    }
    return $path
}
function Test-Workbench([string]$Path) {
    return ($Path -and (Test-Path -LiteralPath (Join-Path $Path 'server.py')) -and
        (Test-Path -LiteralPath (Join-Path $Path 'indextts\utils\presets.py')))
}
function Find-Workbench {
    if ($WorkbenchRoot) {
        if (-not (Test-Workbench $WorkbenchRoot)) { throw 'The selected folder is not a compatible IndexTTS2 Studio root.' }
        return [IO.Path]::GetFullPath($WorkbenchRoot)
    }
    $candidates = @()
    if ($env:INDEXTTS_PROJECT_DIR) { $candidates += $env:INDEXTTS_PROJECT_DIR }
    $settings = Join-Path $packRoot 'runtime\settings.local.json'
    if (Test-Path -LiteralPath $settings) { $candidates += (Read-Json $settings).workbench_root }
    $parent = Split-Path -Parent $packRoot
    $candidates += @($parent, (Join-Path $parent 'IndexTTS2-Studio'),
        (Join-Path $parent 'runtime\IndexTTS2-Studio'), (Join-Path $parent 'runtime\workbench'),
        (Join-Path $env:USERPROFILE 'IndexTTS2-Studio'))
    $localConfig = Join-Path $parent 'config\pipeline.json'
    if (Test-Path -LiteralPath $localConfig) {
        $value = (Read-Json $localConfig).speech.workbench.project_dir
        if ($value) {
            if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $parent $value }
            $candidates += $value
        }
    }
    foreach ($candidate in $candidates) { if (Test-Workbench $candidate) { return [IO.Path]::GetFullPath($candidate) } }
    if ($NonInteractive) { throw 'Workbench not found. Pass -WorkbenchRoot or set INDEXTTS_PROJECT_DIR.' }
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Select the installed IndexTTS2 Studio folder (contains server.py).'
    $dialog.ShowNewFolderButton = $false
    try {
        if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw 'No workbench selected. Nothing was imported.' }
        if (-not (Test-Workbench $dialog.SelectedPath)) { throw 'Select the workbench root containing server.py and indextts/utils/presets.py.' }
        return [IO.Path]::GetFullPath($dialog.SelectedPath)
    } finally { $dialog.Dispose() }
}
function Assert-Hash([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw ('Missing file: ' + $Path) }
    if ((Get-Sha256 $Path) -ne $Expected) {
        throw ('SHA256 mismatch: ' + $Path)
    }
}

try {
    Write-Host 'NJAU-CEA fixed voice pack: XiaoXu boy-v2 + XiaoHe girl-v2'
    $manifest = Read-Json (Join-Path $packRoot 'PACKAGE_MANIFEST.json')
    foreach ($entry in $manifest.files.PSObject.Properties) {
        Assert-Hash (Get-SafeChild $packRoot $entry.Name) $entry.Value
    }
    $profile = Read-Json (Join-Path $packRoot 'voice-profile.json')
    if ($profile.voices.Count -ne 2) { throw 'This pack must contain exactly two fixed voices.' }
    foreach ($voice in $profile.voices) {
        if ($voice.preset -notmatch '^NJAU-CEA-xiao(Xu-boy|He-girl)-v2$') { throw 'Unexpected preset name.' }
        Assert-Hash (Get-SafeChild $packRoot ('presets/' + $voice.preset + '/prompt.wav')) $voice.reference_sha256
    }
    if ($VerifyOnly) { Write-Host 'PASS: all package files and both reference WAVs match.'; exit 0 }
    $workbench = Find-Workbench
    $presetsRoot = Get-SafeChild $workbench 'outputs/presets'
    $jobs = @()
    # Preflight BOTH voices before any preset write. Same-name differences stop.
    foreach ($voice in $profile.voices) {
        $source = Get-SafeChild $packRoot ('presets/' + $voice.preset)
        $target = Get-SafeChild $presetsRoot $voice.preset
        $exists = Test-Path -LiteralPath $target
        if ($exists) {
            foreach ($file in @('prompt.wav', 'preset.json')) {
                $expected = Get-Sha256 (Join-Path $source $file)
                Assert-Hash (Get-SafeChild $target $file) $expected
            }
        }
        $jobs += [PSCustomObject]@{ name = $voice.preset; source = $source; target = $target; exists = $exists }
    }
    [IO.Directory]::CreateDirectory($presetsRoot) | Out-Null
    foreach ($job in $jobs) {
        if ($job.exists) { Write-Host ('Already enabled: ' + $job.name); continue }
        $stage = Get-SafeChild $presetsRoot ('.njau-stage-' + [Guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($stage) | Out-Null
        foreach ($file in @('prompt.wav', 'preset.json')) {
            [IO.File]::Copy((Join-Path $job.source $file), (Join-Path $stage $file), $false)
            Assert-Hash (Join-Path $stage $file) (Get-Sha256 (Join-Path $job.source $file))
        }
        [IO.Directory]::Move($stage, $job.target)
        Write-Host ('Enabled: ' + $job.name)
    }
    $runtime = Get-SafeChild $packRoot 'runtime'
    [IO.Directory]::CreateDirectory($runtime) | Out-Null
    [IO.File]::WriteAllText((Join-Path $runtime 'settings.local.json'), (@{ workbench_root = $workbench } | ConvertTo-Json), $utf8)
    $receipt = @{ status = 'imported'; version = $profile.version; presets = @($jobs.name); api_verified = $false; model_synthesis_performed = $false }
    if (-not $NoLaunch) {
        $url = $null
        function Get-LiveUrl {
            foreach ($file in @('workbench-service.json', 'njau-voicepack-service.json')) {
                $statePath = Join-Path $workbench ('logs\' + $file)
                if (-not (Test-Path -LiteralPath $statePath)) { continue }
                $state = Read-Json $statePath
                if (-not $state.root -or [IO.Path]::GetFullPath($state.root).TrimEnd('\') -ne $workbench.TrimEnd('\')) { continue }
                $uri = [Uri]$state.url
                if ($uri.Scheme -ne 'http' -or $uri.Host -notin @('127.0.0.1', 'localhost', '[::1]')) { throw 'Workbench state must use a local HTTP address.' }
                try {
                    $health = Invoke-RestMethod -Uri ($state.url.TrimEnd('/') + '/api/v1/health') -TimeoutSec 2
                    if ($health.status -eq 'ok') { return $state.url.TrimEnd('/') }
                } catch { continue }
            }
            return $null
        }
        $url = Get-LiveUrl
        if (-not $url) {
            $python = $null
            foreach ($relative in @('.venv\Scripts\python.exe', 'venv\Scripts\python.exe', 'runtime\python.exe', 'python\python.exe', 'python.exe')) {
                $candidate = Join-Path $workbench $relative
                if (Test-Path -LiteralPath $candidate -PathType Leaf) { $python = $candidate; break }
            }
            if (-not $python) { throw 'Voices imported, but the installed workbench Python was not found. Finish its setup, start it, and rerun this tool.' }
            $registryPath = Join-Path $env:USERPROFILE '.Codex\port-registry.json'
            $registry = [PSCustomObject]@{ ports = [PSCustomObject]@{} }
            if (Test-Path -LiteralPath $registryPath) { $registry = Read-Json $registryPath }
            if (-not $registry.ports) { $registry | Add-Member -NotePropertyName ports -NotePropertyValue ([PSCustomObject]@{}) -Force }
            $port = 7861
            while ($port -le 7899) {
                $reserved = $registry.ports.PSObject.Properties[[string]$port]
                if ($reserved -and $reserved.Value.path -ne $workbench) { $port++; continue }
                $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $port)
                try { $listener.Start(); break } catch { $port++ } finally { $listener.Stop() }
            }
            if ($port -gt 7899) { throw 'No free workbench port in 7861-7899. Voices remain imported.' }
            $logs = Get-SafeChild $workbench 'logs'
            [IO.Directory]::CreateDirectory($logs) | Out-Null
            $logId = [Guid]::NewGuid().ToString('N')
            $arguments = 'server.py --host 127.0.0.1 --port ' + $port
            # Keep supported low-memory precision flags without assuming every release has them.
            $serverText = [IO.File]::ReadAllText((Join-Path $workbench 'server.py'))
            foreach ($flag in @('--fp16', '--s2mel_fp16', '--w2v_fp16')) {
                if ($serverText.Contains('"' + $flag + '"') -or $serverText.Contains("'" + $flag + "'")) { $arguments += ' ' + $flag }
            }
            if ($serverText.Contains('"--gpt_batch"') -or $serverText.Contains("'--gpt_batch'")) { $arguments += ' --gpt_batch 0' }
            $proc = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $workbench -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs ($logId + '.voicepack.out.log')) -RedirectStandardError (Join-Path $logs ($logId + '.voicepack.err.log'))
            $state = @{ root = $workbench; url = ('http://127.0.0.1:' + $port); port = $port; pid = $proc.Id }
            [IO.File]::WriteAllText((Join-Path $logs 'njau-voicepack-service.json'), ($state | ConvertTo-Json), $utf8)
            Write-Host 'Starting the installed workbench. No model synthesis is requested.'
            for ($attempt = 0; $attempt -lt 120; $attempt++) {
                $url = Get-LiveUrl
                if ($url) { break }
                if ($proc.HasExited -and $proc.ExitCode -ne 0) { throw 'Workbench startup failed. Voices remain imported; check its logs folder.' }
                Start-Sleep -Milliseconds 1000
            }
            if (-not $url) { throw 'Workbench startup timed out. Voices remain imported; check its logs folder.' }
            $registry.ports | Add-Member -NotePropertyName ([string]$port) -NotePropertyValue (@{ project = 'IndexTTS2 Longform Workbench'; path = $workbench; role = 'web'; updated = (Get-Date -Format 'yyyy-MM-dd') }) -Force
            [IO.Directory]::CreateDirectory((Split-Path -Parent $registryPath)) | Out-Null
            [IO.File]::WriteAllText($registryPath, ($registry | ConvertTo-Json -Depth 12), $utf8)
        }
        foreach ($voice in $profile.voices) {
            $detail = Invoke-RestMethod -Uri ($url + '/api/v1/presets/' + $voice.preset) -TimeoutSec 15
            $expected = Read-Json (Join-Path $packRoot ('presets/' + $voice.preset + '/preset.json'))
            foreach ($key in @('emo_control_method', 'emo_weight', 'emo_text', 'emo_random')) {
                if ($detail.$key -ne $expected.$key) { throw ('Native parameter readback failed: ' + $voice.preset + '/' + $key) }
            }
            if ($detail.emo_vector.Count -ne 8) { throw 'Native emotion vector is incomplete.' }
            for ($i = 0; $i -lt 8; $i++) {
                if ($detail.emo_vector[$i] -ne $expected.emo_vector[$i]) { throw 'Native emotion vector mismatch.' }
            }
            foreach ($property in $expected.advanced_params.PSObject.Properties) {
                if ($detail.advanced_params.($property.Name) -ne $property.Value) { throw ('Native advanced parameter mismatch: ' + $property.Name) }
            }
            if (-not $detail.prompt_audio_url) { throw ('Native reference is missing: ' + $voice.preset) }
            $client = New-Object Net.WebClient
            try { $stream = $client.DownloadData($url + $detail.prompt_audio_url) } finally { $client.Dispose() }
            $hasher = [Security.Cryptography.SHA256]::Create()
            try { $downloadSha = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() } finally { $hasher.Dispose() }
            if ($downloadSha -ne $voice.reference_sha256) { throw ('Native reference readback failed: ' + $voice.preset) }
        }
        $receipt.status = 'enabled_and_api_verified'; $receipt.api_verified = $true
        if (-not $NoBrowser) { Start-Process ($url + '/') }
    }
    [IO.File]::WriteAllText((Join-Path $runtime 'activation-receipt.json'), ($receipt | ConvertTo-Json -Depth 8), $utf8)
    Write-Host 'PASS: both fixed voices are enabled. Select their presets in the workbench.'
    Write-Host 'News pacing 280-300 CPM is a post-processing rule; it is not a native preset speed guarantee.'
    exit 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Existing different presets are never overwritten. Read README.md for import and recovery.'
    exit 1
}
