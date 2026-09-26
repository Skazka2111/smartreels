[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Invoke-Checked {
    param([string]$FilePath, [string[]]$ArgumentList)
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $FilePath" }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw "Python was not found. Install Python 3.13 x64 or run the GitHub Actions workflow."
}
$Python = $PythonCommand.Source
$PythonArgs = @()
Invoke-Checked $Python @(
    "-c",
    "import sys; assert (3, 11) <= sys.version_info[:2] < (3, 14), 'Python 3.11-3.13 x64 is required'; assert sys.maxsize > 2**32, '64-bit Python is required'"
)
$Venv = Join-Path $Root ".windows-build-venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { Invoke-Checked $Python ($PythonArgs + @("-m", "venv", $Venv)) }
Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $VenvPython @("-m", "pip", "install", ".[build]")

$BuildRoot = Join-Path $Root "build\windows"
$StageRoot = Join-Path $Root "artifacts\windows\staging"
if (Test-Path $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
if (Test-Path $StageRoot) { Remove-Item -LiteralPath $StageRoot -Recurse -Force }
New-Item -ItemType Directory -Path $BuildRoot, $StageRoot -Force | Out-Null

Invoke-Checked $VenvPython @(
    "-m", "PyInstaller", "--noconfirm", "--clean",
    "--workpath", $BuildRoot, "--distpath", $StageRoot,
    (Join-Path $Root "packaging\windows\SmartReelsStudio.spec")
)
$PortableDir = Join-Path $StageRoot "Smart Reels Studio"
Copy-Item -Path (Join-Path $Root "portable_template\*") -Destination $PortableDir -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $PortableDir "Smart_Reels_Project\results") -Force | Out-Null

$Cache = Join-Path $Root ".windows-build-cache"
$Archive = Join-Path $Cache "ffmpeg.zip"
$Extract = Join-Path $Cache "ffmpeg"
New-Item -ItemType Directory -Path $Cache -Force | Out-Null
if (-not (Test-Path $Archive)) {
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $Archive
}
if (Test-Path $Extract) { Remove-Item -LiteralPath $Extract -Recurse -Force }
Expand-Archive -LiteralPath $Archive -DestinationPath $Extract -Force
$Ffmpeg = Get-ChildItem $Extract -Filter "ffmpeg.exe" -File -Recurse | Select-Object -First 1
$Ffprobe = Get-ChildItem $Extract -Filter "ffprobe.exe" -File -Recurse | Select-Object -First 1
if (-not $Ffmpeg -or -not $Ffprobe) { throw "FFmpeg was not found in downloaded archive" }
Copy-Item $Ffmpeg.FullName (Join-Path $PortableDir "ffmpeg.exe") -Force
Copy-Item $Ffprobe.FullName (Join-Path $PortableDir "ffprobe.exe") -Force

$Zip = Join-Path $Root "artifacts\windows\Smart_Reels_Studio_Windows_x64_v010.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "Build completed: $Zip" -ForegroundColor Green
