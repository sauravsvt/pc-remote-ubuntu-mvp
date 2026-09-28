"""Allowlisted Windows controls for PC Remote. Python standard library only.

The phone calls the same action names as on Ubuntu. Handlers here run fixed
Windows APIs and one fixed audio script. Caller text never becomes a command.
Per-monitor DDC/CI is not offered on Windows; screen actions affect all displays.
"""
import os
import shutil
import subprocess
from functools import partial
from pathlib import Path
from typing import Callable, NamedTuple

POWERSHELL = "powershell.exe"
SCRIPT = Path(__file__).with_name("windows_audio.ps1")
AUDIO_ACTIONS = {"get", "set", "mute", "unmute"}


def run(args, timeout=20):
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "Command failed").strip()[:250])
    return completed.stdout.strip()


def audio_args(action, value=None):
    if action not in AUDIO_ACTIONS:
        raise ValueError("Unknown audio action")
    if not SCRIPT.is_file():
        raise RuntimeError("Windows audio script is missing")
    args = [POWERSHELL, "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT), "-Action", action]
    if action == "set":
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("Volume must be 0–100")
        args.extend(["-Value", str(value)])
    return args


def monitors():
    return []


def audio():
    if os.name != "nt" or not shutil.which(POWERSHELL):
        return {"available": False}
    try:
        volume, muted = run(audio_args("get")).split()
        return {"available": True, "volume": int(volume), "muted": muted == "1"}
    except (RuntimeError, ValueError):
        return {"available": False}


def x11_available():
    return False


def screens_available():
    return os.name == "nt"


def lock_workstation():
    if os.name != "nt":
        raise RuntimeError("Lock is only available on Windows.")
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not user32.LockWorkStation():
        raise RuntimeError("Lock failed")


def lock():
    lock_workstation()


def set_mute(muted):
    run(audio_args("mute" if muted else "unmute"))


def set_volume(body):
    value = body.get("value")
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("Volume must be 0–100")
    run(audio_args("set", value))


def set_screen_power(state):
    if state not in {"off", "on"}:
        raise ValueError("Unknown screen state")
    if os.name != "nt":
        raise RuntimeError("Screen control is only available on Windows.")
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendMessageTimeoutW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
        ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = ctypes.c_void_p
    result = ctypes.c_size_t()
    # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER. 2 is off, -1 is on.
    sent = user32.SendMessageTimeoutW(
        0xFFFF, 0x0112, 0xF170, 2 if state == "off" else -1, 0x0002, 1000, ctypes.byref(result),
    )
    if not sent:
        raise RuntimeError("Could not change screen power")


def set_screens(state):
    set_screen_power(state)


def leaving():
    warnings = []
    try:
        set_mute(True)
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
    "mute": Action(partial(set_mute, True)),
    "unmute": Action(partial(set_mute, False)),
    "volume": Action(set_volume, needs_body=True),
    "screens-off": Action(partial(set_screens, "off")),
    "screens-on": Action(partial(set_screens, "on")),
    "leaving": Action(leaving),
}
