param(
    [string]$Python = 'python',
    [string]$DistPath = (Join-Path $PSScriptRoot '..\runloom-windows'),
    [string]$WorkPath = (Join-Path $PSScriptRoot 'work\pyinstaller'),
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'Build the Windows distribution on Windows.'
}
if (-not $SkipInstall) {
    & $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
}
& $Python -m PyInstaller --noconfirm --distpath $DistPath --workpath $WorkPath (Join-Path $PSScriptRoot 'runloom.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
Write-Output "Built $DistPath\RunloomDesk\RunloomDesk.exe"
Write-Output 'Distribute the complete RunloomDesk folder; the worker and _internal directory are required.'
