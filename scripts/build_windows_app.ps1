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
  "libexpat.dll"
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
  "--add-data", "requirements.txt;.",
  "--add-data", "scripts;scripts"
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

Write-Host "Building LiteratureAgentSetup.exe..."
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name LiteratureAgentSetup `
  --distpath dist `
  --workpath build `
  @BinaryArgs `
  @DataArgs `
  literature_agent_app.py

$ReleaseDir = Join-Path $ProjectDir "dist\LiteratureAgent"
if (Test-Path $ReleaseDir) {
  Remove-Item -Recurse -Force $ReleaseDir
}
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Copy-Item -Recurse -Force (Join-Path $ProjectDir "dist\LiteratureAgentSetup\*") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir "config.json") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir ".env.example") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir "README.md") $ReleaseDir
Copy-Item -Force (Join-Path $ProjectDir "requirements.txt") $ReleaseDir
Copy-Item -Recurse -Force (Join-Path $ProjectDir "scripts") $ReleaseDir

@"
# Literature Agent Quick Start

1. Double-click `LiteratureAgentSetup.exe`.
2. Fill in the fields marked with a red `*`.
3. Use Feishu, email, or both as notification channels.
4. For QQ Mail, select QQ Mail and enter only the QQ email address plus SMTP authorization code.
5. Click the test buttons for the channels you enabled.
6. Set the daily time and click `Install / Update Windows Task`.

The app creates a local `.env` file next to the executable. Keep that file private.
"@ | Set-Content -Encoding UTF8 (Join-Path $ReleaseDir "QUICK_START.md")

Write-Host ""
Write-Host "Build complete:"
Write-Host $ReleaseDir
Write-Host ""
Write-Host "Share the whole dist\LiteratureAgent folder as a zip package."
