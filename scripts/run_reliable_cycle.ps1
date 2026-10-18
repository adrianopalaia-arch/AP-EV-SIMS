param([Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference='Stop'
$taskRepo=(Resolve-Path -LiteralPath $Repository).Path
$taskPython=Join-Path $taskRepo '.venv\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $taskPython)){throw 'Repository Python environment missing'}
Set-Location -LiteralPath $taskRepo
$env:PYTHONPATH=Join-Path $taskRepo 'src'
$env:PYTHONIOENCODING='utf-8'
$taskLog=Join-Path $taskRepo 'data\evaluations\scheduled-cycle.log'
& $taskPython -m ap_evsims.reliable_engine --root $taskRepo --collect --daily-cap 24 --reserve 50 *> $taskLog
exit $LASTEXITCODE
