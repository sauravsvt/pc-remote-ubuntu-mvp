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
function Find-Pythonw {
  $candidates = @()
  foreach ($name in @("pythonw", "python")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($exe) { $candidates += $exe.Trim() }
  }
  $roots = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python"),
    "C:\Python",
    (Join-Path $env:ProgramFiles "Python")
  )
  foreach ($root in $roots) {
    if (Test-Path -LiteralPath $root) {
      $candidates += @(Get-ChildItem -Path $root -Filter pythonw.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
  }
  foreach ($path in $candidates) {
    if (-not $path) { continue }
    $pythonw = $path
    if ($pythonw -match "python\.exe$") { $pythonw = $pythonw -replace "python\.exe$", "pythonw.exe" }
    if (Test-Path -LiteralPath $pythonw) { return $pythonw }
  }
  return $null
}
function Install-Python {
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
  $version = "3.14.7"
  $name = "python-$version-$arch.exe"
  $dest = Join-Path $env:TEMP $name
  Write-Output "Python 3 was not found. Downloading the official Python $version installer..."
  Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$version/$name" -OutFile $dest
  $signature = Get-AuthenticodeSignature -FilePath $dest
  $trusted = $signature.Status -eq "Valid" -and $signature.SignerCertificate -and ($signature.SignerCertificate.Subject -match "Python Software Foundation")
  if (-not $trusted) {
    Remove-Item -LiteralPath $dest -Force
    throw "The Python installer signature was not valid. Nothing was installed."
  }
  Write-Output "Installing Python for the current user. A progress window will appear."
  $proc = Start-Process -FilePath $dest -ArgumentList @(
    "/passive", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "Include_test=0", "Include_doc=0"
  ) -Wait -PassThru
  if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
    throw "The Python installer exited with code $($proc.ExitCode)."
  }
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

$pythonw = Find-Pythonw
if (-not $pythonw) {
  Install-Python
  $pythonw = Find-Pythonw
}
if (-not $pythonw) { throw "Python 3 was installed, but pythonw.exe still could not be found." }
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
