"""Allowlisted Ubuntu controls for PC Remote. Python standard library only.

To add a control, write a handler here and register it in ACTIONS. Handlers run
fixed commands only. A handler that needs a JSON body must validate every field
it uses before running anything; caller text never becomes a command or shell.
"""
import os
import shutil
import subprocess
from functools import partial
from typing import Callable, NamedTuple

SINK = "@DEFAULT_SINK@"


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
        value = run(["wpctl", "get-volume", SINK])
        return {"available": True, "volume": round(float(value.split()[1]) * 100), "muted": "[MUTED]" in value}
    except (RuntimeError, ValueError, IndexError):
        return {"available": False}


def x11_available():
    return bool(os.environ.get("DISPLAY")) and bool(shutil.which("xset"))


def lock():
    run(["loginctl", "lock-sessions"])


def set_mute(state):
    run(["wpctl", "set-mute", SINK, state])


def set_volume(body):
    value = body.get("value")
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("Volume must be 0–100")
    run(["wpctl", "set-volume", SINK, f"{value}%"])


def set_screens(state):
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("X11 display unavailable. See Wayland note in README.")
    run(["xset", "+dpms"])
    run(["xset", "dpms", "force", state])


def set_monitor_power(mode, body):
    number = body.get("id")
    if type(number) is not int or number not in [m["id"] for m in monitors()]:
        raise ValueError("Monitor is not currently detected")
    run(["ddcutil", "setvcp", "d6", mode, "--display", str(number)], 20)


def leaving():
    warnings = []
    try:
        set_mute("1")
    except RuntimeError as exc:
        warnings.append("Mute: " + str(exc))
    lock()
    try:
        set_screens("off")
    except RuntimeError as exc:
        warnings.append("Screens: " + str(exc))
    return {"ok": True, "warnings": warnings}


class Action(NamedTuple):
    handler: Callable
    needs_body: bool = False


ACTIONS = {
    "lock": Action(lock),
    "mute": Action(partial(set_mute, "1")),
    "unmute": Action(partial(set_mute, "0")),
    "volume": Action(set_volume, needs_body=True),
    "screens-off": Action(partial(set_screens, "off")),
    "screens-on": Action(partial(set_screens, "on")),
    "monitor-standby": Action(partial(set_monitor_power, "04"), needs_body=True),
    "monitor-on": Action(partial(set_monitor_power, "01"), needs_body=True),
    "leaving": Action(leaving),
}
