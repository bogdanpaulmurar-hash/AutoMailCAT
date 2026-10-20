"""Application state shared by the web server, the tray icon and the engines."""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path

from . import __version__, model, system
from .store import LocalSettings, TeamStore, pc_name, user_name
from .worker import TeamWorker

LOG = logging.getLogger("automailcat.app")


def team_id(folder: str) -> str:
    return hashlib.sha1(str(Path(folder)).lower().encode("utf-8")).hexdigest()[:10]


class App:
    def __init__(self, data_dir: Path, web_dir: Path, app_dir: Path, demo: bool = False):
        self.data_dir = Path(data_dir)
        self.web_dir = web_dir
        self.app_dir = app_dir
        self.demo = demo
        self.settings = LocalSettings(self.data_dir)
        self.keep_awake = system.KeepAwake(lambda: self.settings.get().get("keep_awake", False))
        self.workers: dict[str, TeamWorker] = {}
        self.on_quit = None
        self.log_path: Path | None = None
        if demo:
            self._prepare_demo()

    # ── teams ───────────────────────────────────────────────────────────
    def _prepare_demo(self):
        folder = self.data_dir / "demo-team"
        store = TeamStore(folder)
        if not store.exists():
            from .demo import create_demo_team
            create_demo_team(store)
        s = self.settings.get()
        if not any(Path(t["folder"]) == folder for t in s["teams"]):
            s["teams"].insert(0, {"folder": str(folder), "engine": True, "demo": True})
            self.settings.update({"teams": s["teams"]})

    def teams(self) -> list[dict]:
        out = []
        for t in self.settings.get()["teams"]:
            tid = team_id(t["folder"])
            store = TeamStore(t["folder"])
            name = store.team()["name"] if store.exists() else Path(t["folder"]).name
            worker = self.workers.get(tid)
            out.append({"id": tid, "folder": t["folder"], "name": name, "engine": t.get("engine", True),
                        "demo": bool(t.get("demo")), "reachable": store.exists(),
                        "status": worker.status() if worker else {"role": "stopped"}})
        return out

    def team_entry(self, tid: str) -> dict:
        for t in self.settings.get()["teams"]:
            if team_id(t["folder"]) == tid:
                return t
        raise KeyError("team_not_found")

    def store(self, tid: str) -> TeamStore:
        return TeamStore(self.team_entry(tid)["folder"])

    def worker(self, tid: str) -> TeamWorker | None:
        return self.workers.get(tid)

    def start_engines(self):
        for t in self.settings.get()["teams"]:
            self._start(t)

    def _start(self, t: dict):
        tid = team_id(t["folder"])
        if tid in self.workers:
            return
        if not TeamStore(t["folder"]).exists():
            LOG.warning("Team folder not reachable: %s", t["folder"])
        w = TeamWorker(t["folder"], demo=bool(t.get("demo")) or self.demo, keep_awake=self.keep_awake,
                       enabled=t.get("engine", True))
        self.workers[tid] = w
        w.start()

    def stop_engines(self):
        for w in self.workers.values():
            w.stop()
        self.workers.clear()

    def add_team(self, folder: str, name: str = "", mailbox: str = "", language: str = "ro") -> dict:
        folder = str(Path(folder))
        store = TeamStore(folder)
        if not store.exists():
            if not name:
                raise ValueError("name_required")
            store.initialize(name, mailbox, language)
        s = self.settings.get()
        if not any(team_id(t["folder"]) == team_id(folder) for t in s["teams"]):
            s["teams"].append({"folder": folder, "engine": True})
            self.settings.update({"teams": s["teams"]})
        entry = self.team_entry(team_id(folder))
        self._start(entry)
        return {"id": team_id(folder)}

    def remove_team(self, tid: str):
        s = self.settings.get()
        s["teams"] = [t for t in s["teams"] if team_id(t["folder"]) != tid]
        self.settings.update({"teams": s["teams"]})
        w = self.workers.pop(tid, None)
        if w:
            w.stop()

    def set_engine_enabled(self, tid: str, enabled: bool):
        s = self.settings.get()
        for t in s["teams"]:
            if team_id(t["folder"]) == tid:
                t["engine"] = enabled
        self.settings.update({"teams": s["teams"]})
        w = self.workers.get(tid)
        if w:
            w.enabled = enabled

    # ── misc ────────────────────────────────────────────────────────────
    def can_edit(self, team: dict) -> bool:
        editors = [e.lower() for e in team.get("editors") or []]
        return not editors or user_name().lower() in editors

    def info(self) -> dict:
        s = self.settings.get()
        return {
            "version": __version__, "user": user_name(), "pc": pc_name(), "demo": self.demo,
            "devpilot": system.MANAGED_BY_DEVPILOT,
            "devpilot_owns": {f: system.devpilot_owns(f) for f in ("tray", "keepawake", "autostart")},
            "settings": {k: v for k, v in s.items() if k != "teams"},
            "autostart": system.autostart_enabled(), "today": date.today().isoformat(),
            "teams": self.teams(),
            "exceptions": list(model.EXCEPTIONS),
        }
