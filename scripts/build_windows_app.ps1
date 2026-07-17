$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonExe = "D:\work_program\anaconda3\envs\pynep\python.exe"

if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

Set-Location $ProjectDir

$PythonPrefix = (& $PythonExe -c "import sys; print(sys.prefix)").Trim()
$CondaBin = Join-Path $PythonPrefix "Library\bin"
$TclLib = Join-Path $PythonPrefix "Library\lib\tcl8.6"
$TkLib = Join-Path $PythonPrefix "Library\lib\tk8.6"

$BinaryArgs = @()
foreach ($dll in @(
  "tcl86t.dll",
  "tk86t.dll",
  "sqlite3.dll",
  "libssl-3-x64.dll",
  "libcrypto-3-x64.dll",
  "liblzma.dll",
  "libbz2.dll",
  "libexpat.dll",
  "ffi.dll"
)) {
  $dllPath = Join-Path $CondaBin $dll
  if (Test-Path $dllPath) {
    $BinaryArgs += @("--add-binary", "$dllPath;.")
  }
}

$DataArgs = @(
  "--add-data", "README.md;.",
  "--add-data", "config.json;.",
  "--add-data", ".env.example;.",
  "--add-data", "requirements.txt;."
)
if (Test-Path $TclLib) {
  $DataArgs += @("--add-data", "$TclLib;tcl\tcl8.6")
}
if (Test-Path $TkLib) {
  $DataArgs += @("--add-data", "$TkLib;tcl\tk8.6")
}

Write-Host "Checking PyInstaller..."
& $PythonExe -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "PyInstaller is not installed. Installing it with pip..."
  & $PythonExe -m pip install pyinstaller
}

Write-Host "Checking CustomTkinter..."
& $PythonExe -c "import customtkinter" *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "CustomTkinter is not installed. Installing it with pip..."
  & $PythonExe -m pip install customtkinter
}

Write-Host "Building LiteratureAgentSetup.exe..."
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name LiteratureAgentSetup `
  --distpath dist `
  --workpath build `
  --collect-data customtkinter `
  --hidden-import customtkinter `
  --hidden-import darkdetect `
  @BinaryArgs `
  @DataArgs `
  literature_agent_app.py

$ReleaseDir = Join-Path $ProjectDir "dist\LiteratureAgent"
$ReleaseZip = Join-Path $ProjectDir "dist\LiteratureAgent-Windows.zip"
if (Test-Path $ReleaseDir) {
  Remove-Item -Recurse -Force $ReleaseDir
}
if (Test-Path $ReleaseZip) {
  Remove-Item -Force $ReleaseZip
}
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Copy-Item -Recurse -Force (Join-Path $ProjectDir "dist\LiteratureAgentSetup\*") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir "config.json") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir ".env.example") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir "README.md") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir "requirements.txt") $ReleaseDir

$ReleaseScriptsDir = Join-Path $ReleaseDir "scripts"
New-Item -ItemType Directory -Force -Path $ReleaseScriptsDir | Out-Null
Copy-Item -Force (Join-Path $ProjectDir "scripts\install_windows_task.ps1") $ReleaseScriptsDir

@'
# Literature Agent Quick Start

1. Extract this ZIP to a normal local folder such as `Documents\LiteratureAgent`.
2. Double-click `LiteratureAgentSetup.exe`. Python and PowerShell are not required for normal use.
3. Enter the LLM API values and enable Feishu and/or email.
4. Run the relevant test buttons, then click `Save Configuration`.
5. To use this computer for local scheduling, set a daily time and click `Install / Update Windows Task`.

The app creates `.env`, `data`, and `reports` only after it is configured or run. These files are private runtime data and must not be shared.
'@ | Set-Content -Encoding UTF8 (Join-Path $ReleaseDir "QUICK_START.md")

$BlockedNames = @(".env", "data", "reports", "logs", "__pycache__")
$BlockedFiles = @("*.pyc", "*.pyo")
$BlockedEntries = Get-ChildItem -Force -Recurse $ReleaseDir | Where-Object {
  $entry = $_
  ($BlockedNames -contains $_.Name) -or
  ($entry.PSIsContainer -eq $false -and ($BlockedFiles | Where-Object { $entry.Name -like $_ }))
}
if ($BlockedEntries) {
  $BlockedEntries | ForEach-Object { Write-Host "Blocked release entry: $($_.FullName)" }
  throw "Release package contains runtime data or Python cache files."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
  $ReleaseDir,
  $ReleaseZip,
  [System.IO.Compression.CompressionLevel]::Optimal,
  $true
)

Write-Host ""
Write-Host "Build complete:"
Write-Host $ReleaseDir
Write-Host $ReleaseZip
Write-Host ""
Write-Host "Share only the newly generated LiteratureAgent-Windows.zip."
