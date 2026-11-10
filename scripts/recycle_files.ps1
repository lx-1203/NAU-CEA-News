param([Parameter(Mandatory=$true)][string]$InputFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName Microsoft.VisualBasic

function Assert-Physical([string]$Path) {
    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw 'Absolute paths required' }
    $absolute = [System.IO.Path]::GetFullPath($Path)
    $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($absolute))
    if ($drive.DriveType -ne [System.IO.DriveType]::Fixed) { throw 'Only local fixed drives are authorized' }
    $item = $absolute
    while ($item) {
        if (Test-Path -LiteralPath $item) {
            $attributes = (Get-Item -LiteralPath $item -Force).Attributes
            if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse points forbidden' }
        }
        $parent = [System.IO.Directory]::GetParent($item)
        if ($null -eq $parent) { break }
        $item = $parent.FullName
    }
    return $absolute
}

$request = Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8 | ConvertFrom-Json
$scope = (Assert-Physical ([string]$request.scope)).TrimEnd('\')
if (-not (Test-Path -LiteralPath $scope -PathType Container)) { throw 'Missing authorized scope' }
$results = @()
foreach ($candidate in $request.paths) {
    try {
        $path = Assert-Physical ([string]$candidate)
        if (-not $path.StartsWith($scope + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Candidate escapes authorized scope' }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Only existing individual files may be recycled' }
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
            $path,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
            [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException)
        $results += @{path=[string]$candidate; status='recycled'}
    } catch {
        $results += @{path=[string]$candidate; status='error'; reason=$_.Exception.Message}
    }
}
ConvertTo-Json -InputObject @($results) -Compress
