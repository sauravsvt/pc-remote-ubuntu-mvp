$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $env:LOCALAPPDATA "pc-remote"
$files = @("agent.py", "actions.py", "windows_actions.py", "windows_audio.ps1", "index.html")
New-Item -ItemType Directory -Force -Path $target | Out-Null
foreach ($file in $files) {
  $from = Join-Path $source $file
  if (-not (Test-Path -LiteralPath $from)) { throw "Missing $from" }
  Copy-Item -LiteralPath $from -Destination (Join-Path $target $file) -Force
}
$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { throw "pythonw.exe was not found. Install Python 3 and enable Add to PATH." }
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and $_.CommandLine.Contains((Join-Path $target "agent.py"))
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
$taskAction = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$target\agent.py`"" -WorkingDirectory $target
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "PC Remote" -Action $taskAction -Trigger $trigger -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName "PC Remote"
Start-Sleep -Seconds 1
Write-Output "PC Remote installed. Open http://127.0.0.1:8765 on this PC."
Write-Output "Your private token is in $env:APPDATA\pc-remote\token"
Write-Output "Read README.md before enabling remote access."
