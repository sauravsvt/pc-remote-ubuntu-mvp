#!/usr/bin/env python3
"""Small, local-only Ubuntu control service. Python standard library only."""
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HOST = "127.0.0.1"
PORT = int(os.environ.get("PC_REMOTE_PORT", "8765"))
DATA = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "pc-remote"
TOKEN_FILE = DATA / "token"
UI = Path(__file__).with_name("index.html")


def token():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    if not TOKEN_FILE.exists():
        fd = os.open(TOKEN_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
    if TOKEN_FILE.stat().st_mode & 0o077:
        raise RuntimeError("Token file must be private (chmod 600)")
    return TOKEN_FILE.read_text().strip()


SECRET = token()


def run(args, timeout=8):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "Command failed").strip()[:250])
    return p.stdout.strip()


def monitors():
    if not shutil.which("ddcutil"):
        return []
    try:
        out = run(["ddcutil", "detect", "--brief"], 20)
    except RuntimeError:
        return []
    found = []
    current = None
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Display ") and line[8:].strip().isdigit():
            current = {"id": int(line[8:].strip()), "name": "Monitor " + line[8:].strip()}
            found.append(current)
        elif current and line.startswith("Model:"):
            current["name"] = line.partition(":")[2].strip()[:80]
    return found


def audio():
    if not shutil.which("wpctl"):
        return {"available": False}
    try:
        value = run(["wpctl", "get-volume", "@DEFAULT_SINK@"])
        return {"available": True, "volume": round(float(value.split()[1]) * 100), "muted": "[MUTED]" in value}
    except (RuntimeError, ValueError, IndexError):
        return {"available": False}


def status():
    up = 0
    try:
        up = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        pass
    return {"device": socket.gethostname(), "uptime_seconds": up, "audio": audio(),
            "monitors": monitors(), "x11": bool(os.environ.get("DISPLAY")) and bool(shutil.which("xset")),
            "session": os.environ.get("XDG_SESSION_TYPE", "unknown")}


def action(name, body):
    if name == "lock":
        run(["loginctl", "lock-sessions"])
    elif name == "mute":
        run(["wpctl", "set-mute", "@DEFAULT_SINK@", "1"])
    elif name == "unmute":
        run(["wpctl", "set-mute", "@DEFAULT_SINK@", "0"])
    elif name == "volume":
        value = body.get("value")
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("Volume must be 0–100")
        run(["wpctl", "set-volume", "@DEFAULT_SINK@", f"{value}%"])
    elif name in ("screens-off", "screens-on"):
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("X11 display unavailable. See Wayland note in README.")
        run(["xset", "+dpms"])
        run(["xset", "dpms", "force", "off" if name == "screens-off" else "on"])
    elif name in ("monitor-standby", "monitor-on"):
        number = body.get("id")
        if type(number) is not int or number not in [m["id"] for m in monitors()]:
            raise ValueError("Monitor is not currently detected")
        run(["ddcutil", "setvcp", "d6", "04" if name == "monitor-standby" else "01", "--display", str(number)], 20)
    elif name == "leaving":
        warnings = []
        try:
            run(["wpctl", "set-mute", "@DEFAULT_SINK@", "1"])
        except RuntimeError as exc:
            warnings.append("Mute: " + str(exc))
        run(["loginctl", "lock-sessions"])
        if os.environ.get("DISPLAY"):
            try:
                run(["xset", "+dpms"])
                run(["xset", "dpms", "force", "off"])
            except RuntimeError as exc:
                warnings.append("Screens: " + str(exc))
        else:
            warnings.append("Screens: X11 display unavailable")
        return {"ok": True, "warnings": warnings}
    else:
        raise ValueError("Unknown action")
    return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + SECRET)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = UI.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not self.authorized():
            return self.reply(401, {"error": "Invalid token"})
        if self.path == "/api/status":
            return self.reply(200, status())
        self.reply(404, {"error": "Not found"})

    def do_POST(self):
        # A browser on an unrelated site cannot issue a valid authenticated request.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if not origin or urlsplit(origin).netloc != host or not self.authorized():
            return self.reply(403, {"error": "Denied"})
        if not self.path.startswith("/api/"):
            return self.reply(404, {"error": "Not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 1024:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Expected object")
            result = action(self.path[5:], body)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.reply(400, {"error": str(exc)})
        except RuntimeError as exc:
            return self.reply(503, {"error": str(exc)})
        self.reply(200, result)


if __name__ == "__main__":
    print(f"PC Remote listening on http://{HOST}:{PORT}; token in {TOKEN_FILE}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
