"""AutoMailCAT — start the app.

    start.bat                       interface in the browser + icon next to the clock + engine
    start.bat --tray                same, without opening the browser (start with Windows)
    start.bat --no-tray             no tray icon (stop with Ctrl+C or from the interface)
    start.bat --demo                fictional team and mailbox, no Outlook needed
    start.bat --action sweep        tell the running app to: sweep | pause | resume | report | quit
    start.bat --data D              keep settings and logs in folder D
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from amc import __version__, system, tray  # noqa: E402
from amc.app import App  # noqa: E402
from amc.server import Server  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="automailcat", description="AutoMailCAT " + __version__)
    ap.add_argument("--data", type=Path, default=Path(os.environ.get("AUTOMAILCAT_DATA", system.default_data_dir())))
    ap.add_argument("--tray", action="store_true", help="started at login: do not open the browser")
    ap.add_argument("--no-tray", action="store_true")
    ap.add_argument("--demo", action="store_true", help="fictional team and mailbox (no Outlook)")
    ap.add_argument("--port", type=int)
    ap.add_argument("--action", choices=["open", "sweep", "pause", "resume", "report", "quit"])
    ap.add_argument("--team", default="", help="with --action: only this team (name)")
    args = ap.parse_args(argv)

    data_dir = args.data / "demo" if args.demo else args.data
    data_dir.mkdir(parents=True, exist_ok=True)
    app = App(data_dir, ROOT / "web", ROOT, demo=args.demo)
    settings = app.settings.get()
    port = args.port or int(settings["port"]) + (1 if args.demo else 0)
    url = f"http://127.0.0.1:{port}/"

    if args.action:
        if args.action == "open":
            if system.forward_action(port, "noop"):
                webbrowser.open(url)
                return 0
        elif system.forward_action(port, args.action, args.team):
            return 0
        if args.action != "open":
            print("AutoMailCAT is not running on this PC.")
            return 1

    app.log_path = system.setup_logging(data_dir)
    log = logging.getLogger("automailcat")
    log.info("AutoMailCAT %s starting (demo=%s, devpilot=%s)", __version__, args.demo, system.MANAGED_BY_DEVPILOT)

    try:
        server = Server(app, port)
    except OSError as exc:
        log.error("Port %s is busy (already running?): %s", port, exc)
        webbrowser.open(url)
        return 1
    server.start()
    app.start_engines()

    stop = threading.Event()

    def quit_app():
        stop.set()

    app.on_quit = quit_app
    if not args.tray and settings.get("open_browser_on_start", True):
        webbrowser.open(url if app.teams() else url + "#/setup")

    use_tray = tray.AVAILABLE and not args.no_tray and not system.devpilot_owns("tray")
    if not tray.AVAILABLE and not args.no_tray and not system.devpilot_owns("tray"):
        log.warning("Tray icon not available: run install.bat (pystray, Pillow)")
    try:
        if use_tray:
            tray.Tray(app, url, quit_app).run()
        else:
            try:
                signal.signal(signal.SIGINT, lambda *_: stop.set())
            except ValueError:
                pass
            print(f"AutoMailCAT running at {url}  (Ctrl+C to stop)")
            while not stop.wait(0.5):
                pass
    finally:
        app.stop_engines()
        server.stop()
        log.info("AutoMailCAT stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
