#!/usr/bin/env python3
"""Small, local-only Ubuntu control service. Python standard library only."""
import hmac
import json
import os
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import actions

API_VERSION = "1"
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


def status():
    up = 0
    try:
        up = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        pass
    return {"api": API_VERSION, "device": socket.gethostname(), "actions": list(actions.ACTIONS),
            "uptime_seconds": up, "audio": actions.audio(), "monitors": actions.monitors(),
            "x11": actions.x11_available(), "session": os.environ.get("XDG_SESSION_TYPE", "unknown")}


def dispatch(name, body):
    entry = actions.ACTIONS.get(name)
    if entry is None:
        raise ValueError("Unknown action")
    if entry.needs_body:
        result = entry.handler(body)
    elif body:
        raise ValueError("This action takes no arguments")
    else:
        result = entry.handler()
    return result or {"ok": True}


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
            result = dispatch(self.path[len("/api/"):], body)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.reply(400, {"error": str(exc)})
        except RuntimeError as exc:
            return self.reply(503, {"error": str(exc)})
        self.reply(200, result)


if __name__ == "__main__":
    print(f"PC Remote listening on http://{HOST}:{PORT}; token in {TOKEN_FILE}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
