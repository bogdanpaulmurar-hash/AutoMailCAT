"""Files of one team (in its shared folder) and the local settings of this PC.

Writes are atomic (temporary file + rename) and versioned: every document
carries `_rev`; saving with an older `_rev` raises Conflict, so the team
leader and the stand-in cannot overwrite each other's changes unnoticed.
Sync clients (OneDrive / Teams) sometimes lock a file for a moment, so
writes are retried.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import model

LOG = logging.getLogger("automailcat.store")


class Conflict(Exception):
    """The document was changed by someone else since it was loaded."""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def user_name() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "user"


def pc_name() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        LOG.warning("Cannot read %s: %s", path, exc)
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    for attempt in range(6):
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.25 * (attempt + 1))
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class TeamStore:
    def __init__(self, folder: Path | str):
        self.folder = Path(folder)
        self._thread_cache: tuple[float, dict] = (0.0, {})

    # ── paths ───────────────────────────────────────────────────────────
    def path(self, name: str) -> Path:
        return self.folder / name

    def plan_path(self, day: date) -> Path:
        return self.folder / "plans" / f"{day.isoformat()}.json"

    def state_path(self, day: date) -> Path:
        return self.folder / "state" / f"{day.isoformat()}.json"

    def journal_path(self, day: date) -> Path:
        return self.folder / "journal" / f"{day.isoformat()}.jsonl"

    def exists(self) -> bool:
        return (self.folder / "team.json").exists()

    # ── versioned documents ─────────────────────────────────────────────
    def _load(self, path: Path, default) -> dict:
        data = read_json(path, None)
        if data is None:
            data = default
        if isinstance(data, list):
            data = {"items": data}
        data.setdefault("_rev", 0)
        return data

    def _save(self, path: Path, data: dict, expected_rev: int | None, by: str = "") -> dict:
        current = read_json(path, None) or {}
        cur_rev = int(current.get("_rev", 0)) if isinstance(current, dict) else 0
        if expected_rev is not None and int(expected_rev) != cur_rev:
            raise Conflict(path.name)
        data = dict(data)
        data["_rev"] = cur_rev + 1
        data["_by"] = by or user_name()
        data["_at"] = now_iso()
        write_json(path, data)
        return data

    def team(self) -> dict:
        raw = self._load(self.path("team.json"), {})
        t = model.normalize_team(raw)
        for k in ("_rev", "_by", "_at"):
            t[k] = raw.get(k, 0 if k == "_rev" else "")
        return t

    def save_team(self, team: dict, rev: int | None, by: str = "") -> dict:
        clean = {k: v for k, v in model.normalize_team(team).items()}
        return self._save(self.path("team.json"), clean, rev, by)

    def agents(self) -> tuple[list[dict], int]:
        raw = self._load(self.path("agents.json"), {"agents": []})
        return model.normalize_agents(raw.get("agents", raw.get("items", []))), int(raw["_rev"])

    def save_agents(self, agents: list[dict], rev: int | None, by: str = "") -> int:
        doc = self._save(self.path("agents.json"), {"agents": model.normalize_agents(agents)}, rev, by)
        return doc["_rev"]

    def rules(self) -> tuple[list[dict], int]:
        raw = self._load(self.path("rules.json"), {"rules": []})
        return model.normalize_rules(raw.get("rules", raw.get("items", []))), int(raw["_rev"])

    def save_rules(self, rules: list[dict], rev: int | None, by: str = "") -> int:
        doc = self._save(self.path("rules.json"), {"rules": model.normalize_rules(rules)}, rev, by)
        return doc["_rev"]

    # ── plans ───────────────────────────────────────────────────────────
    def plan(self, day: date) -> dict | None:
        raw = read_json(self.plan_path(day), None)
        if raw is None:
            return None
        p = model.normalize_plan(raw, day)
        p["_rev"] = int(raw.get("_rev", 0))
        p["_by"], p["_at"] = raw.get("_by", ""), raw.get("_at", "")
        return p

    def save_plan(self, day: date, plan: dict, rev: int | None, by: str = "") -> dict:
        clean = model.normalize_plan(plan, day)
        clean["history"] = (clean.get("history") or [])[-200:]
        saved = self._save(self.plan_path(day), clean, rev, by)
        return self.plan(day) or saved

    def previous_plan(self, day: date, max_days: int = 31) -> dict | None:
        for back in range(1, max_days + 1):
            p = self.plan(day - timedelta(days=back))
            if p:
                return p
        return None

    def plan_dates(self) -> list[str]:
        folder = self.folder / "plans"
        if not folder.exists():
            return []
        return sorted((p.stem for p in folder.glob("*.json")), reverse=True)

    # ── rotation state (engine only) ────────────────────────────────────
    def rotation(self, day: date) -> dict:
        return dict((read_json(self.state_path(day), {}) or {}).get("rotation", {}))

    def save_rotation(self, day: date, rotation: dict) -> None:
        write_json(self.state_path(day), {"rotation": rotation, "_by": pc_name(), "_at": now_iso()})

    # ── journal ─────────────────────────────────────────────────────────
    def journal_append(self, day: date, entry: dict) -> None:
        path = self.journal_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        for attempt in range(6):
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                return
            except PermissionError:
                time.sleep(0.25 * (attempt + 1))

    def journal(self, day: date) -> list[dict]:
        path = self.journal_path(day)
        out = []
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except ValueError:
                            continue
        except FileNotFoundError:
            pass
        return out

    def processed_ids(self, days: int = 3) -> set[str]:
        today = date.today()
        ids = set()
        for back in range(days + 1):
            for e in self.journal(today - timedelta(days=back)):
                if e.get("id") and e.get("status") in ("ok", "manual", "reassigned"):
                    ids.add(e["id"])
        return ids

    def thread_owners(self, days: int = 30) -> dict:
        """conversation id -> agent id, newest wins (cached for a minute)."""
        stamp, cached = self._thread_cache
        if time.time() - stamp < 60:
            return cached
        owners: dict = {}
        today = date.today()
        for back in range(days, -1, -1):
            for e in self.journal(today - timedelta(days=back)):
                if e.get("conv") and e.get("agent") and e.get("status") in ("ok", "manual", "reassigned"):
                    owners[e["conv"]] = e["agent"]
        self._thread_cache = (time.time(), owners)
        return owners

    def forget_thread_cache(self):
        self._thread_cache = (0.0, {})

    # ── engine lock ─────────────────────────────────────────────────────
    def read_lock(self) -> dict:
        return read_json(self.path("engine.lock.json"), {}) or {}

    def write_lock(self, info: dict) -> None:
        write_json(self.path("engine.lock.json"), info)

    # ── set-up ──────────────────────────────────────────────────────────
    def initialize(self, name: str, mailbox: str = "", language: str = "ro") -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        if not self.path("team.json").exists():
            self._save(self.path("team.json"), model.normalize_team(
                {"name": name, "mailbox": mailbox, "language": language,
                 "fallback_category": "De verificat" if language == "ro" else "To check"}), None)
        if not self.path("agents.json").exists():
            self._save(self.path("agents.json"), {"agents": []}, None)
        if not self.path("rules.json").exists():
            self._save(self.path("rules.json"), {"rules": []}, None)


# ── local settings of this PC ───────────────────────────────────────────

SETTINGS_DEFAULTS = {
    "language": "ro",
    "port": 8767,
    "open_browser_on_start": True,
    "keep_awake": False,          # keep the PC awake while the engine runs
    "autostart": False,
    "teams": [],                  # [{"folder": "...", "engine": true}]
    "last_team": "",
}


class LocalSettings:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "settings.json"

    def get(self) -> dict:
        raw = read_json(self.path, {}) or {}
        out = dict(SETTINGS_DEFAULTS)
        out.update({k: v for k, v in raw.items() if k in SETTINGS_DEFAULTS})
        out["teams"] = [t for t in out["teams"] if isinstance(t, dict) and t.get("folder")]
        return out

    def update(self, changes: dict) -> dict:
        cur = self.get()
        cur.update({k: v for k, v in changes.items() if k in SETTINGS_DEFAULTS})
        write_json(self.path, cur)
        return cur
