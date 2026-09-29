# PC Remote

PC Remote is a local control page for one Linux or Windows computer. From a phone on your private [Tailscale](https://tailscale.com/) network you can lock the session, set the volume, and turn the displays off. The computer keeps running.

There is no account server, remote shell, screen streaming, or remote desktop. Each computer is a separate install, with its own token and its own address. The source is [MIT licensed](LICENSE). Copyright © 2026 Saurav Shriwastav.

The public homepage lives in [`site/`](site/index.html) and is intended for `https://pcremote.voxonlabs.com/`.

## Controls

| Control | What it does |
| --- | --- |
| Lock | Locks the current desktop session. |
| Mute, unmute, volume | Controls the default audio output. |
| Leaving | Mutes, locks, and turns the displays off. |
| All screens off / wake | Turns every display off or on. The computer and its jobs keep running. |
| Per-monitor standby and wake | Linux only, when DDC/CI can see the monitor. |

On Linux, screen control uses X11 DPMS. Mouse movement can wake the displays. On Wayland the screen buttons are disabled; lock and audio still work. DDC/CI support depends on the monitor, cable, graphics adapter, and the monitor's own menu. A display may stop accepting commands while it is asleep, so try Wake once while you are at the desk. Laptop built-in panels usually do not appear in DDC discovery. The page reports that a command was accepted. It does not measure power use or confirm the panel state.

On Windows, screen actions affect every display together. Per-monitor DDC/CI buttons are not offered. Mouse or keyboard activity may wake the displays. Confirm lock, volume, and screen power once on the Windows machine before relying on them away from the desk.

## Install on Linux

Requirements: Python 3, a systemd user session, and `loginctl`. Audio uses PipeWire (`wpctl`). Screen power uses `xset` on X11. Per-monitor control uses `ddcutil`. On Ubuntu those packages are commonly `wireplumber`, `x11-xserver-utils`, `ddcutil`, and `i2c-tools`. Enable DDC/CI in each monitor menu if you use per-monitor buttons. The desktop user may need access to `/dev/i2c-*`.

Sign in to the graphical session, then from this directory:

```bash
bash install.sh
cat ~/.config/pc-remote/token
```

The service starts with your user session. It is not set up to run before login. Open `http://127.0.0.1:8765` on that computer and enter the token.

To install from the public page, after it is published:

```bash
curl -fsSL https://pcremote.voxonlabs.com/install.sh | bash
```

Review [`site/install.sh`](site/install.sh) before piping it to a shell. It downloads this repository and runs `install.sh`. Run it as the desktop user, not as root.

## Install on Windows

Install Python 3 from [python.org](https://www.python.org/downloads/windows/) and enable **Add python.exe to PATH**, including `pythonw.exe`. From this directory in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
Get-Content "$env:APPDATA\pc-remote\token"
```

The installer copies the application to `%LOCALAPPDATA%\pc-remote` and starts it at sign-in. Open `http://127.0.0.1:8765` on that PC and enter the token. If the page does not load, run `python agent.py` from `%LOCALAPPDATA%\pc-remote` in a console and read the error.

Download the repository in the browser or with `Invoke-WebRequest`, extract it, and run `install.ps1` from that folder. Do not pipe a remote script into `iex`. Windows Defender treats that pattern as a trojan dropper and blocks `powershell.exe`.

```powershell
cd $env:USERPROFILE\Downloads
Invoke-WebRequest https://github.com/sauravsvt/pc-remote-ubuntu-mvp/archive/refs/heads/main.zip -OutFile pc-remote.zip
Expand-Archive .\pc-remote.zip -DestinationPath . -Force
cd .\pc-remote-ubuntu-mvp-main
Unblock-File .\install.ps1
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

## Connect a phone

The agent listens only on `127.0.0.1:8765`. Tailscale Serve gives the phone a private HTTPS address on your tailnet. Do not enable Tailscale Funnel, and do not forward port 8765 on your router.

1. Install [Tailscale on the computer](https://tailscale.com/download) and sign in. On Linux:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

2. Install the Tailscale app on the phone from the App Store or Google Play and sign in to the same account. Both devices should show as connected.
3. On the computer, publish the local page to the tailnet:

```bash
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

On Windows, if PowerShell cannot find `tailscale`, call `& "C:\Program Files\Tailscale\tailscale.exe"` instead. If the command reports a permission error, run it with administrator rights.

4. Open the `https://…ts.net` address from `tailscale serve status` in the phone browser, enter the token, and add the page to the home screen.

The token stays in that browser until the session ends or you press **Forget token**. Keep the token on your own devices. To add another computer, repeat the install there. The phone controls whichever address it opens.

Tailscale provides the network. The application runs on the computer. A self-hosted WireGuard or Headscale network can replace Tailscale later.

## Security

Every API call requires a 256-bit bearer token. Actions also require a browser `Origin` whose host matches the request `Host`. The server accepts only named actions and checks numeric fields before it runs anything. Caller text is never passed to a shell.

On Linux the token file is mode `0600` at `~/.config/pc-remote/token`. On Windows it is at `%APPDATA%\pc-remote\token` and restricted to the current user. To replace a lost token, write a new file there, restart the service, and enter the new token on the phone. Removing a device from the tailnet removes its network access.

The service does not suspend, reboot, shut down, launch applications, or open a terminal.

`GET /api/status` returns API version `"1"`, the hostname, the platform, and the action names that computer supports. The page shows only those controls.

## Troubleshooting

On Linux:

```bash
systemctl --user status pc-remote.service
journalctl --user -u pc-remote.service -n 50
echo "$XDG_SESSION_TYPE $DISPLAY"
ddcutil detect --brief
```

If the user service has no X11 `DISPLAY`, import the graphical session and restart:

```bash
systemctl --user import-environment DISPLAY XAUTHORITY XDG_SESSION_TYPE
systemctl --user restart pc-remote.service
```

Re-running `bash install.sh` copies the current files and restarts the service.

## Development

```bash
python3 -m unittest test_agent.py
```

Linux actions live in [`actions.py`](actions.py). Windows actions live in [`windows_actions.py`](windows_actions.py). A new control is one handler, one registry entry, and one label in [`index.html`](index.html).

## Remove

On Linux, `tailscale serve reset` removes every Serve route on that host. Skip it when other services use Serve, and remove only this route instead.

```bash
systemctl --user disable --now pc-remote.service
tailscale serve reset
rm -f ~/.config/systemd/user/pc-remote.service
rm -rf ~/.local/share/pc-remote ~/.config/pc-remote
systemctl --user daemon-reload
```

On Windows:

```powershell
Unregister-ScheduledTask -TaskName "PC Remote" -Confirm:$false
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\pc-remote", "$env:APPDATA\pc-remote"
```
