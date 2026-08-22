param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

$Version = (& uv run --extra build python -c "import eql_combat_feed; print(eql_combat_feed.__version__)").Trim()
if (-not $Version) { throw "Unable to determine application version." }

Write-Host "Building EQL Combat Feed $Version"
Remove-Item -Recurse -Force "$ProjectRoot\build\windows", "$ProjectRoot\dist\EQL Combat Feed" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$ProjectRoot\build\windows" | Out-Null

$VersionParts = @($Version.Split('.') | ForEach-Object { [int]$_ })
while ($VersionParts.Count -lt 4) { $VersionParts += 0 }
$VersionTuple = ($VersionParts[0..3] -join ', ')
$VersionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($VersionTuple), prodvers=($VersionTuple), mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'zenoran'),
      StringStruct('FileDescription', 'EQL Combat Feed'),
      StringStruct('FileVersion', '$Version'),
      StringStruct('InternalName', 'eql-combat-feed'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 zenoran'),
      StringStruct('OriginalFilename', 'EQL Combat Feed.exe'),
      StringStruct('ProductName', 'EQL Combat Feed'),
      StringStruct('ProductVersion', '$Version'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"@
$GeneratedVersionInfo = "$ProjectRoot\build\windows\version_info.txt"
Set-Content -Path $GeneratedVersionInfo -Value $VersionInfo -Encoding UTF8

uv run --extra build pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "EQL Combat Feed" `
    --icon "$ProjectRoot\assets\icons\eql-combat-feed.ico" `
    --version-file $GeneratedVersionInfo `
    --distpath "$ProjectRoot\dist" `
    --workpath "$ProjectRoot\build\windows\pyinstaller" `
    --specpath "$ProjectRoot\build\windows" `
    "$ProjectRoot\packaging\windows\entrypoint.py"

$Exe = "$ProjectRoot\dist\EQL Combat Feed\EQL Combat Feed.exe"
if (-not (Test-Path $Exe)) { throw "PyInstaller did not produce $Exe" }
& $Exe --version

if ($SkipInstaller) {
    Write-Host "Portable application built at: $Exe"
    exit 0
}

$IsccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 is required. Install it with: winget install --id JRSoftware.InnoSetup --exact"
}

& $Iscc "/DAppVersion=$Version" "$ProjectRoot\packaging\windows\installer.iss"
$Installer = "$ProjectRoot\dist\EQL-Combat-Feed-Setup-$Version.exe"
if (-not (Test-Path $Installer)) { throw "Inno Setup did not produce $Installer" }
Write-Host "Installer built at: $Installer"
