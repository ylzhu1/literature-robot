$ProjectDir = "D:\agent_Crawling_Literature"
$PythonExe = "D:\work_program\anaconda3\envs\pynep\python.exe"
$TaskName = "LiteratureAgentDailyBrief"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m literature_agent.main --config config.json --send-feishu" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Daily -At 9:00
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily literature brief email from Literature Agent" -Force
Write-Host "Installed scheduled task: $TaskName"
