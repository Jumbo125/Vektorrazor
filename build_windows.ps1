# Build and prepare a GitHub Release asset for Windows AMD64.
# Run from PowerShell: powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RootDir = Split-Path -Parent $PSCommandPath
Set-Location $RootDir

$AppName = 'Vektorrazor'
$Platform = 'Windows-amd64'
$Version = (Get-Content -Raw -LiteralPath (Join-Path $RootDir 'VERSION')).Trim()
if ($Version -notmatch '^\d+(\.\d+){1,3}([+-][0-9A-Za-z.-]+)?$') {
    throw "VERSION enthaelt keine gueltige Versionsnummer: '$Version'"
}

# Windows resource versions require exactly four numeric components.  A
# prerelease suffix is kept in the textual metadata but omitted from FileVersion.
$NumericVersion = ($Version -split '[+-]', 2)[0]
$VersionParts = @($NumericVersion -split '\.')
while ($VersionParts.Count -lt 4) { $VersionParts += '0' }
$WindowsVersion = $VersionParts[0..3] -join '.'

$AssetBaseName = "$AppName-$Version-$Platform"
$BuildDir = Join-Path $RootDir 'build'
$StageRoot = Join-Path $BuildDir 'release'
$StageDir = Join-Path $StageRoot $AssetBaseName
$ReleaseDir = Join-Path $RootDir 'release'
$Archive = Join-Path $ReleaseDir "$AssetBaseName.zip"
$Checksum = "$Archive.sha256"
$GeneratedVersionInfo = Join-Path $BuildDir 'version_info.generated.txt'

New-Item -ItemType Directory -Force -Path $BuildDir, $StageRoot, $ReleaseDir | Out-Null
Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

# Derive the EXE metadata from VERSION so it cannot get out of sync with the
# release filename. Keep the source version_info.txt unchanged.
$VersionInfo = Get-Content -Raw -LiteralPath (Join-Path $RootDir 'version_info.txt')
$VersionInfo = $VersionInfo -replace "filevers=\([^\)]*\)", "filevers=($($WindowsVersion -replace '\.', ', '))"
$VersionInfo = $VersionInfo -replace "prodvers=\([^\)]*\)", "prodvers=($($WindowsVersion -replace '\.', ', '))"
$VersionInfo = $VersionInfo -replace "StringStruct\('FileVersion', '[^']*'\)", "StringStruct('FileVersion', '$Version')"
$VersionInfo = $VersionInfo -replace "StringStruct\('ProductVersion', '[^']*'\)", "StringStruct('ProductVersion', '$Version')"
$VersionInfo = $VersionInfo -replace "StringStruct\('OriginalFilename', '[^']*'\)", "StringStruct('OriginalFilename', '$AppName.exe')"
Set-Content -LiteralPath $GeneratedVersionInfo -Value $VersionInfo -Encoding utf8

python -m PyInstaller `
    --onefile `
    --windowed `
    --clean `
    --name $AppName `
    --icon 'assets\vektorrazor.ico' `
    --version-file $GeneratedVersionInfo `
    --hidden-import=PIL._tkinter_finder `
    --hidden-import=PIL.ImageTk `
    --collect-submodules=PIL `
    --add-data 'assets\vektorrazor.ico;assets' `
    --add-data 'assets\vektorrazor_icon.png;assets' `
    main.py

Copy-Item -LiteralPath (Join-Path $RootDir "dist\$AppName.exe") -Destination (Join-Path $StageDir "$AppName.exe")
foreach ($File in 'README.md', 'README.de.md', 'README.en.md', 'LICENSE', 'NOTICE.md', 'AUTHORS.md') {
    if (Test-Path -LiteralPath (Join-Path $RootDir $File) -PathType Leaf) {
        Copy-Item -LiteralPath (Join-Path $RootDir $File) -Destination $StageDir
    }
}

Remove-Item -LiteralPath $Archive, $Checksum -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $StageDir -DestinationPath $Archive -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $Checksum -Value "$Hash *$AssetBaseName.zip" -Encoding ascii

Write-Host 'GitHub-Release-Artefakte erstellt:'
Write-Host "  $Archive"
Write-Host "  $Checksum"
