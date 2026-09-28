$ErrorActionPreference = "Stop"
$repo = "sauravsvt/pc-remote-ubuntu-mvp"
$ref = if ($env:PC_REMOTE_REF) { $env:PC_REMOTE_REF } else { "main" }
if ($ref.StartsWith("v")) {
  $url = "https://github.com/$repo/archive/refs/tags/$ref.zip"
} else {
  $url = "https://github.com/$repo/archive/refs/heads/$ref.zip"
}
$tmp = Join-Path $env:TEMP ("pc-remote-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  $zip = Join-Path $tmp "src.zip"
  Invoke-WebRequest -Uri $url -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $tmp
  $src = Get-ChildItem -Directory $tmp | Where-Object { $_.Name -like "pc-remote-ubuntu-mvp-*" } | Select-Object -First 1
  if (-not $src) { throw "Downloaded archive did not contain the project." }
  & (Join-Path $src.FullName "install.ps1")
  Write-Output "Next, open https://pcremote.voxonlabs.com/#phone and connect Tailscale."
} finally {
  Remove-Item -Recurse -Force $tmp
}
