param([string]$Repository=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$taskRepo=(Resolve-Path -LiteralPath $Repository).Path
$taskName='AP-EV-SIMS-Verified-Research'
$taskRunner=Join-Path $taskRepo 'scripts\run_reliable_cycle.ps1'
if(-not (Test-Path -LiteralPath $taskRunner)){throw 'Runner script missing'}
$taskExecutable=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$taskArguments='-NoProfile -NonInteractive -WindowStyle Hidden -File "'+$taskRunner+'" -Repository "'+$taskRepo+'"'
$taskOld=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if($taskOld){
    if($taskOld.Actions.Execute -ne $taskExecutable -or $taskOld.Actions.Arguments -ne $taskArguments){throw 'Existing task has a different action; refusing to replace it'}
} else {
    $taskAction=New-ScheduledTaskAction -Execute $taskExecutable -Argument $taskArguments -WorkingDirectory $taskRepo
    $taskTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 365)
    $taskPrincipal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $taskSettings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'Local hash-verified sports research and settlement. No wagers or Git writes.' | Out-Null
}
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
