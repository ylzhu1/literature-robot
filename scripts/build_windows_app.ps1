$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonExe = "D:\work_program\anaconda3\envs\pynep\python.exe"

if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

Set-Location $ProjectDir

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
  --add-data "README.md;." `
  --add-data "config.json;." `
  --add-data ".env.example;." `
  --add-data "requirements.txt;." `
  --add-data "scripts;scripts" `
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
2. Fill in the LLM API settings.
3. Fill in the Feishu webhook or email settings.
4. Click `Test LLM` and `Test Feishu`.
5. Set the daily time and click `Install / Update Windows Task`.

The app creates a local `.env` file next to the executable. Keep that file private.
"@ | Set-Content -Encoding UTF8 (Join-Path $ReleaseDir "QUICK_START.md")

Write-Host ""
Write-Host "Build complete:"
Write-Host $ReleaseDir
Write-Host ""
Write-Host "Share the whole dist\LiteratureAgent folder as a zip package."
