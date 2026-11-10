param([Parameter(Mandatory=$true)][string]$TextFile,[Parameter(Mandatory=$true)][string]$OutputFile,[Parameter(Mandatory=$true)][string]$Voice)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice($Voice)
    $speaker.Rate = 1
    $speaker.SetOutputToWaveFile($OutputFile)
    $speaker.Speak([IO.File]::ReadAllText($TextFile, [Text.Encoding]::UTF8))
} finally { $speaker.Dispose() }
