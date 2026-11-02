$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
$taskPython=Join-Path $taskRoot '.venv/Scripts/pythonw.exe'
if(-not (Test-Path -LiteralPath $taskPython)){
    $taskPython=(Get-Command python -ErrorAction Stop).Source
}
try{$taskRunning=Invoke-RestMethod 'http://127.0.0.1:8785/api/state' -TimeoutSec 2}catch{$taskRunning=$null}
if(-not $taskRunning){
    Start-Process -FilePath $taskPython -ArgumentList @(('"'+(Join-Path $PSScriptRoot 'server.py')+'"')) -WorkingDirectory $taskRoot -WindowStyle Hidden
}
Start-Process 'http://127.0.0.1:8785'
