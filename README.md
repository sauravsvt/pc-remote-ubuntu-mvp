# PC Remote — small Ubuntu prototype

A local phone-sized control page for one Ubuntu computer. Install it independently on each machine. It has no account server, cloud database, remote shell, AI agent, terminal, or background screen streaming. Source is MIT licensed.

## Connect from your phone

The phone never talks to port 8765 on the public internet. Install the agent on the Ubuntu desktop, then put Tailscale Serve in front of the loopback server so only your tailnet can open it.

1. On the Ubuntu desktop, logged into the graphical session, from this directory:

```bash
bash install.sh
cat ~/.config/pc-remote/token
```

2. Install Tailscale on this PC and on the phone, signed into the same tailnet.
3. On the PC, expose the agent to your tailnet only (check `tailscale serve --help` on your installed version):

```bash
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

4. Open the HTTPS tailnet URL from `tailscale serve status` on the phone, enter the token, and add the page to the home screen.
5. Do not use Tailscale Funnel or router port forwarding. Limit tailnet access to your own phone and account, especially before adding a family or office machine. A token is required in addition to private network access. Never share the token in chat or a screenshot.

You can also open `http://127.0.0.1:8765` on the computer itself and enter the token. The token stays in the browser's session storage until that tab or session ends, or you press **Forget token**. The agent starts with your user session. It is not configured for unattended use before login.

If the screen buttons are disabled, the session is Wayland; lock and audio still work. If `DISPLAY` is missing from the user service, import the graphical session's environment, then restart (commands below).

To add another computer, repeat the install there and give that machine its own token and tailnet URL. Save each URL as a browser bookmark or home-screen shortcut. The phone page controls the computer whose URL it opens; there is no central fleet dashboard or cross-machine permission system yet. For someone else's computer, install with their consent and use their own account; do not silently enable unattended access.

This setup uses the Tailscale service for connectivity. The app itself is open source and runs locally. If you later want the network coordination self-hosted too, replace Tailscale with your own WireGuard/Headscale setup.

## What works

- Online name, uptime, session type, audio state
- Lock, mute, unmute, set volume, and one-tap Leaving (mute + lock + X11 DPMS screen off)
- All displays off/on using X11 DPMS, while the computer and running jobs continue
- Discover DDC/CI displays; per-display standby/wake is experimental and requires a physical test on each monitor

**Display limitations:** X11 DPMS affects all displays and mouse movement can wake them. On Wayland, the screen buttons are disabled; lock and audio still work. DDC/CI standby support varies by display, graphics adapter, cable, and monitor setting. A monitor may stop responding to DDC commands while asleep. Try its Wake button while at the desk before relying on it remotely. The app reports a command's success, not measured power consumption or confirmed screen state. Laptop built-in displays typically do not appear in DDC discovery.

## Install on Ubuntu desktop

Requirements: Python 3, systemd user services, `loginctl`, PipeWire/WirePlumber (`wpctl`) for audio, and optionally `xset` for X11 screens and `ddcutil` for individual DDC/CI monitors. On Ubuntu, packages are commonly `x11-xserver-utils`, `wireplumber`, `ddcutil`, and `i2c-tools`; verify which are installed on your PC before installing additional packages. Enable DDC/CI in each monitor's own menu if needed. The desktop user may need access to `/dev/i2c-*` for DDC/CI.

To troubleshoot:

```bash
systemctl --user status pc-remote.service
journalctl --user -u pc-remote.service -n 50
echo "$XDG_SESSION_TYPE $DISPLAY"
ddcutil detect --brief
```

If a systemd user service lacks the X11 `DISPLAY` variable, import the graphical session's environment then restart:

```bash
systemctl --user import-environment DISPLAY XAUTHORITY XDG_SESSION_TYPE
systemctl --user restart pc-remote.service
```

## Safety and boundaries

The HTTP server binds only to `127.0.0.1`, checks a 256-bit token on each API call, requires matching browser Origin for actions, and accepts only known operations with validated numeric inputs. It never executes supplied shell text. The token file is created with mode 0600; losing the phone browser token can be handled by restarting the service after replacing `~/.config/pc-remote/token`, then entering the new token on your phone. Revoking a Tailscale device separately removes its network access.

There is no suspend, reboot, shutdown, application launch, terminal, project agent, or remote desktop in this prototype. Those should follow actual use and a separate permission design. Locking, Wayland display control, and per-monitor wake behavior should be verified on your hardware.

## Remove

```bash
systemctl --user disable --now pc-remote.service
tailscale serve reset
rm -f ~/.config/systemd/user/pc-remote.service
rm -rf ~/.local/share/pc-remote ~/.config/pc-remote
systemctl --user daemon-reload
```

`tailscale serve reset` removes **all** Serve configurations on that host, so skip it if you use Serve for other services and remove only this route through your current Tailscale configuration instead.
