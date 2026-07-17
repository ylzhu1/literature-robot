$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$TaskName = "LiteratureAgentDailyBrief"

$Executable = Join-Path $ProjectDir "LiteratureAgentSetup.exe"
$Argument = "--run-daily"
if (-not (Test-Path $Executable)) {
  $Executable = "python"
  $Argument = "-m literature_agent.main --config config.json"
}

$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $ExistingTask) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Action = New-ScheduledTaskAction `
  -Execute $Executable `
  -Argument $Argument `
  -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Daily -At 9:00
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Description "Daily Literature Agent report" `
  -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
