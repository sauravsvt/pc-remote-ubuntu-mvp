param([switch]$PhoneOnly, [string]$ResultFile)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Test-Admin {
  $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
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

function Find-Tailscale {
  $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $path = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
  if (Test-Path -LiteralPath $path) { return $path }
  return $null
}

function Install-Tailscale {
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
  $dest = Join-Path $env:TEMP "tailscale-setup-$arch.msi"
  Write-Output "Downloading Tailscale..."
  Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-latest-$arch.msi" -OutFile $dest
  $signature = Get-AuthenticodeSignature -FilePath $dest
  $trusted = $signature.Status -eq "Valid" -and $signature.SignerCertificate -and ($signature.SignerCertificate.Subject -match "Tailscale")
  if (-not $trusted) {
    Remove-Item -LiteralPath $dest -Force
    throw "The Tailscale installer signature was not valid. Nothing was installed."
  }
  Write-Output "Installing Tailscale. A progress window will appear."
  $proc = Start-Process msiexec.exe -ArgumentList @("/i", $dest, "/passive", "/norestart") -Wait -PassThru
  if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
    throw "The Tailscale installer exited with code $($proc.ExitCode)."
  }
  Start-Sleep -Seconds 3
}

function Get-TailscaleState($cli) {
  $raw = & $cli status --json 2>$null | Out-String
  if (-not $raw) { return $null }
  try { return $raw | ConvertFrom-Json } catch { return $null }
}

function Test-PagePublished($cli) {
  $text = & $cli serve status 2>&1 | Out-String
  return $text -match "127\.0\.0\.1:8765"
}

function Get-PhoneOrigin($cli) {
  $serve = & $cli serve status 2>&1 | Out-String
  $url = [regex]::Match($serve, "https://[A-Za-z0-9.-]+").Value
  if ($url) { return $url.TrimEnd(".") }
  $state = Get-TailscaleState $cli
  $dns = ([string]$state.Self.DNSName).TrimEnd(".")
  if ($dns) { return "https://$dns" }
  return ""
}

function Request-Admin {
  Write-Output "Approve the Windows prompt. It publishes the page on your private Tailscale network."
  $result = Join-Path $env:TEMP "pc-remote-tailscale-setup.txt"
  Remove-Item -LiteralPath $result -Force -ErrorAction SilentlyContinue
  try {
    Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-PhoneOnly", "-ResultFile", $result
    ) | Out-Null
  } catch {
    Write-Output "The prompt was closed. Install Tailscale from https://tailscale.com/download/windows, sign in, then run this installer again."
    return
  }
  $cli = Find-Tailscale
  if ($cli -and (Test-PagePublished $cli)) {
    Show-NextSteps $cli -OpenBrowser
    return
  }
  if (Test-Path -LiteralPath $result) {
    Write-Output (Get-Content -Raw -LiteralPath $result).Trim()
  } else {
    Write-Output "The page is not published yet. Tailscale is already signed in, so run this installer again and approve the prompt."
  }
}

function Publish-Page($cli) {
  $first = & $cli serve --bg --yes "http://127.0.0.1:8765" 2>&1 | Out-String
  if (Test-PagePublished $cli) { return "" }
  $second = & $cli serve --bg "http://127.0.0.1:8765" 2>&1 | Out-String
  if (Test-PagePublished $cli) { return "" }
  return ($first + $second).Trim()
}

function Show-NextSteps($cli, [switch]$OpenBrowser) {
  $public = Get-PhoneOrigin $cli
  $health = ""
  if ($cli) { $health = & $cli status 2>&1 | Out-String }
  $tokenPath = Join-Path $env:APPDATA "pc-remote\token"
  $token = ""
  if (Test-Path -LiteralPath $tokenPath) { $token = (Get-Content -Raw -LiteralPath $tokenPath).Trim() }
  $encoded = [uri]::EscapeDataString($token)
  $local = "http://127.0.0.1:8765/#token=$encoded"
  if ($OpenBrowser -and $token) { Start-Process $local }
  Write-Output ""
  Write-Output "This PC is opening the controls. You do not type the token there."
  if ($public -and $token) {
    Write-Output "On your phone, install the Tailscale app, sign in with the same account, then open:"
    Write-Output "$public/#token=$encoded"
    Write-Output "That link signs the phone in. Add the page to the home screen."
    if ($health -match "Fetching TLS certificate") {
      Write-Output "The phone link can take a minute while Tailscale finishes its certificate. Open it again if the browser complains."
    }
  } else {
    Write-Output "Tailscale is signed in. Run this installer again and it will print the phone link."
  }
  Write-Output "Do not send that link in a chat or a screenshot. Do not turn on Funnel."
}

function Enable-PhoneAccess {
  $cli = Find-Tailscale
  if (-not $cli) {
    if (-not (Test-Admin)) { Request-Admin; return }
    Install-Tailscale
    $cli = Find-Tailscale
  }
  if (-not $cli) { throw "Tailscale was installed, but tailscale.exe still could not be found." }
  $state = Get-TailscaleState $cli
  if ($state -and $state.BackendState -eq "Running") {
    Write-Output "Tailscale is already signed in on this PC."
  } else {
    Write-Output "Sign in to Tailscale if a browser window opens. Use the same account as your phone."
    & $cli up
    if ($LASTEXITCODE -ne 0) { throw "Tailscale sign-in did not finish." }
  }
  if (-not (Test-PagePublished $cli)) {
    $detail = Publish-Page $cli
    if (-not (Test-PagePublished $cli)) {
      if (-not (Test-Admin)) { Request-Admin; return }
      if ($detail) { throw "Could not publish PC Remote on your private Tailscale network. $detail" }
      throw "Could not publish PC Remote on your private Tailscale network."
    }
  }
  if (-not $PhoneOnly) { Show-NextSteps $cli -OpenBrowser }
}

if ($PhoneOnly) {
  try {
    Enable-PhoneAccess
    if ($ResultFile) { "ok" | Set-Content -LiteralPath $ResultFile }
    exit 0
  } catch {
    if ($ResultFile) { $_.Exception.Message | Set-Content -LiteralPath $ResultFile }
    exit 1
  }
}

$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $env:LOCALAPPDATA "pc-remote"
$files = @("agent.py", "actions.py", "windows_actions.py", "windows_audio.ps1", "index.html")
New-Item -ItemType Directory -Force -Path $target | Out-Null
foreach ($file in $files) {
  $from = Join-Path $source $file
  if (-not (Test-Path -LiteralPath $from)) { throw "Missing $from" }
  Copy-Item -LiteralPath $from -Destination (Join-Path $target $file) -Force
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
Enable-PhoneAccess
