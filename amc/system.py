"""Windows integration: data folder, log, keep-awake, start with Windows, DevPilot."""
from __future__ import annotations

import ctypes
import json
import logging
import logging.handlers
import os
import sys
import urllib.request
from pathlib import Path

LOG = logging.getLogger("automailcat.system")

# ── DevPilot (https://github.com/bogdanpaulmurar-hash/DevPilot) ─────────
# When DevPilot starts AutoMailCAT it owns some features; we then skip ours.
_SUPPRESSED = {p.strip().lower() for p in os.environ.get("DEVPILOT_SUPPRESS", "").split(",") if p.strip()}
MANAGED_BY_DEVPILOT = os.environ.get("DEVPILOT_MANAGED") == "1"


def devpilot_owns(feature: str) -> bool:
    """True when DevPilot started this process and owns `feature` ("tray", "keepawake", "autostart")."""
    return MANAGED_BY_DEVPILOT and feature in _SUPPRESSED


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "AutoMailCAT"


def setup_logging(data_dir: Path) -> Path:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "automailcat.log"
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr and not sys.executable.lower().endswith("pythonw.exe"):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        root.addHandler(console)
    return path


# ── keep-awake ──────────────────────────────────────────────────────────
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


class KeepAwake:
    """Asks Windows not to sleep while the engine runs on this PC (no mouse moves, no key presses)."""

    def __init__(self, enabled_fn):
        self.enabled_fn = enabled_fn
        self.active = False

    def __call__(self, want: bool):
        want = bool(want and self.enabled_fn() and not devpilot_owns("keepawake"))
        if os.name != "nt":
            self.active = want
            return
        if want == self.active:
            return
        try:
            flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if want else 0)
            ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
            self.active = want
        except Exception:  # noqa: BLE001
            pass


# ── start with Windows (shortcut-free: a small .cmd in the Startup folder) ─
def startup_file() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "AutoMailCAT.cmd"


def set_autostart(enabled: bool, app_dir: Path) -> bool:
    """Creates or removes the Startup entry. Skipped when DevPilot owns autostart."""
    if devpilot_owns("autostart"):
        return False
    path = startup_file()
    if path is None:
        return False
    if enabled:
        path.write_text(f'@echo off\r\ncd /d "{app_dir}"\r\ncall start.bat --tray\r\n', encoding="ascii", errors="ignore")
    elif path.exists():
        path.unlink()
    return True


def autostart_enabled() -> bool:
    path = startup_file()
    return bool(path and path.exists())


# ── single instance / --action forwarding ───────────────────────────────
def forward_action(port: int, action: str, team: str = "") -> bool:
    """Sends an action to an AutoMailCAT already running on this PC. True when it answered."""
    data = json.dumps({"action": action, "team": team}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/action", data=data, method="POST",
                                 headers={"Content-Type": "application/json", "X-AutoMailCAT": "1"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=5) as resp:
            return resp.status < 300
    except Exception:  # noqa: BLE001
        return False


def pick_folder(title: str = "") -> str:
    """Native folder picker (tkinter, part of Python on Windows). Empty string if unavailable or cancelled."""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title=title or "AutoMailCAT")
        root.destroy()
        return path or ""
    except Exception:  # noqa: BLE001
        return ""
