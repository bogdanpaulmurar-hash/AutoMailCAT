"""Engine of one team: one background thread per team folder.

Only one PC per team runs the engine at a time ("leader"): it writes a
heartbeat to engine.lock.json in the team folder every 30 seconds. Another
PC takes over when the heartbeat is older than the team's `stale_minutes`,
or right away when it is the team's preferred PC.

The leader handles new mails as Outlook reports them, sweeps the source
folder at start-up and every few minutes (mails that arrived while no PC
ran the engine, or that Outlook did not report), and runs the commands
the interface sends it (send the daily message, list folders, reassign).
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
import traceback
import uuid
from concurrent.futures import Future
from datetime import date, datetime

from . import delivery, engine, model, report
from .mailbox import DemoMailbox, MailboxError, since_for
from .store import TeamStore, now_iso, pc_name, user_name

LOG = logging.getLogger("automailcat.worker")
HEARTBEAT_SECONDS = 30


def effective_plan(store: TeamStore, team: dict, day: date) -> dict | None:
    plan = store.plan(day)
    if plan and plan.get("confirmed"):
        return plan
    if team.get("before_confirmation") == "previous_plan":
        prev = plan or store.previous_plan(day)
        if prev:
            return model.plan_from_previous(prev, day)
    return plan


class TeamWorker:
    def __init__(self, folder: str, demo: bool = False, keep_awake=None, enabled: bool = True):
        self.store = TeamStore(folder)
        self.folder = folder
        self.demo = demo
        self.enabled = enabled
        self.keep_awake = keep_awake            # callable(bool) or None
        self.commands: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.paused = False
        self.mailbox = None
        self.role = "stopped"                   # stopped | connecting | leader | standby | error | disabled
        self.message = ""
        self.leader_info: dict = {}
        self.waiting = 0                        # mails waiting for the confirmation of the day
        self.last_sweep = ""
        self.counts = {"ok": 0, "error": 0}
        self._seen: dict[str, int] = {}         # entry id -> attempts (this session)
        self._last_heartbeat = 0.0
        self._next_sweep = 0.0
        self._sweep_requested = True
        self.reconnect_requested = False
        self.token = uuid.uuid4().hex[:12]       # identifies this running engine in engine.lock.json

    # ── public (any thread) ─────────────────────────────────────────────
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name=f"engine:{os.path.basename(self.folder)}", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 5):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout)
        self.role = "stopped"

    def request_sweep(self):
        self._sweep_requested = True

    def call(self, fn, timeout: float = 60):
        """Runs fn(mailbox) on the engine thread (COM objects live there) and returns its result."""
        if not self.thread or not self.thread.is_alive():
            raise MailboxError("engine_not_running")
        fut: Future = Future()
        self.commands.put((fn, fut))
        return fut.result(timeout=timeout)

    def status(self) -> dict:
        return {
            "folder": self.folder, "role": self.role, "message": self.message, "paused": self.paused,
            "leader": self.leader_info, "waiting": self.waiting, "last_sweep": self.last_sweep,
            "counts": dict(self.counts), "demo": self.demo, "pc": pc_name(), "enabled": self.enabled,
        }

    # ── engine thread ───────────────────────────────────────────────────
    def _open_mailbox(self, team: dict):
        if self.demo:
            mb = DemoMailbox(self.folder)
        else:
            from .outlook import OutlookMailbox
            mb = OutlookMailbox(team.get("mailbox", ""), team.get("source_folder", ""),
                                team.get("engine", {}).get("start_outlook", False))
        mb.open()
        return mb

    def _run(self):
        retry_at = 0.0
        while not self.stop_event.is_set():
            try:
                if not self.enabled:
                    self.role = "disabled"
                    self._drain_commands(None)
                    time.sleep(1)
                    continue
                team = self.store.team()
                if self.reconnect_requested:
                    self.reconnect_requested = False
                    self._close_mailbox()
                    retry_at = 0.0
                if self.mailbox is None:
                    if time.time() < retry_at:
                        self._drain_commands(None)
                        time.sleep(1)
                        continue
                    self.role, self.message = "connecting", ""
                    try:
                        self.mailbox = self._open_mailbox(team)
                        self.message = ""
                    except MailboxError as exc:
                        self.role, self.message = "error", str(exc)
                        retry_at = time.time() + 30
                        continue
                self._heartbeat(team)
                self._drain_commands(self.mailbox)
                if self.role == "leader" and not self.paused:
                    for entry_id in self.mailbox.take_new():
                        self._process(entry_id, team)
                    if self._sweep_requested or time.time() >= self._next_sweep:
                        self._sweep(team)
                self.mailbox.pump(1.0)
            except Exception as exc:  # noqa: BLE001  (COM disconnects, Outlook closed, …)
                LOG.error("Engine error: %s\n%s", exc, traceback.format_exc())
                self.role, self.message = "error", str(exc)
                self._close_mailbox()
                retry_at = time.time() + 30
        self._release()
        self._close_mailbox()

    def _close_mailbox(self):
        if self.mailbox is not None:
            try:
                self.mailbox.close()
            except Exception:  # noqa: BLE001
                pass
        self.mailbox = None
        if self.keep_awake:
            self.keep_awake(False)

    def _drain_commands(self, mailbox):
        while True:
            try:
                fn, fut = self.commands.get_nowait()
            except queue.Empty:
                return
            if fut.set_running_or_notify_cancel():
                try:
                    if mailbox is None:
                        raise MailboxError(self.message or "engine_not_connected")
                    fut.set_result(fn(mailbox))
                except Exception as exc:  # noqa: BLE001
                    fut.set_exception(exc)

    # ── leader election ─────────────────────────────────────────────────
    def _heartbeat(self, team: dict):
        if time.time() - self._last_heartbeat < HEARTBEAT_SECONDS and self.role in ("leader", "standby"):
            return
        self._last_heartbeat = time.time()
        me = pc_name()
        lock = self.store.read_lock()
        stale = team["engine"]["stale_minutes"] * 60
        holder = lock.get("pc", "")
        age = time.time() - float(lock.get("beat", 0) or 0)
        preferred = (team["engine"].get("preferred_pc") or "").strip().lower()
        mine = lock.get("token") == self.token
        take = (not holder or age > stale or mine
                or (preferred and preferred == me.lower() and holder.lower() != me.lower()))
        if holder.lower() == me.lower() and not mine and age <= stale:
            take = False          # a second copy on the same PC: stay quiet
        if take:
            was_leader = self.role == "leader"
            info = {"pc": me, "user": user_name(), "pid": os.getpid(), "token": self.token, "beat": time.time(),
                    "since": lock.get("since") if mine else now_iso(), "demo": self.demo}
            self.store.write_lock(info)
            self.leader_info = info
            self.role = "leader"
            if not was_leader:
                LOG.info("Engine active on this PC for %s", self.folder)
                self._sweep_requested = True
            if self.keep_awake:
                self.keep_awake(True)
        else:
            if self.role == "leader":
                LOG.info("Engine handed over to %s", holder)
            self.role = "standby"
            self.leader_info = lock
            if self.keep_awake:
                self.keep_awake(False)

    def _release(self):
        lock = self.store.read_lock()
        if lock.get("token") == self.token:
            lock["beat"] = 0
            self.store.write_lock(lock)

    # ── processing ──────────────────────────────────────────────────────
    def _context(self, team: dict, day: date, plan: dict | None) -> engine.Context:
        agents, _ = self.store.agents()
        rules, _ = self.store.rules()
        return engine.Context(team=team, agents=agents, rules=rules, plan=plan,
                              rotation=self.store.rotation(day), thread_owners=self.store.thread_owners(),
                              now=datetime.now())

    def _sweep(self, team: dict):
        self._sweep_requested = False
        self._next_sweep = time.time() + team["sweep_minutes"] * 60
        processed = self.store.processed_ids(max(1, team["lookback_days"]) + 1)
        waiting = 0
        for entry_id in self.mailbox.scan(since_for(team["lookback_days"])):
            if entry_id in processed or self._seen.get(entry_id, 0) >= 3:
                continue
            if self._process(entry_id, team) == "wait":
                waiting += 1
        self.waiting = waiting
        self.last_sweep = now_iso()

    def _process(self, entry_id: str, team: dict) -> str:
        if self._seen.get(entry_id, 0) >= 3:
            return "skip"
        mail = self.mailbox.read(entry_id)
        if mail is None:
            return "skip"
        day = date.today()
        agents, _ = self.store.agents()
        assigned = {a["category"].lower(): a for a in agents}
        fallback = (team.get("fallback_category") or "").lower()
        existing = [c for c in mail.get("categories", []) if c.lower() in assigned or c.lower() == fallback]
        if existing:            # someone (or an earlier run) already assigned it: respect it
            if self._seen.get(entry_id) is None:
                agent = assigned.get(existing[0].lower())
                self.store.journal_append(day, self._entry(mail, entry_id, "manual", agent=agent["id"] if agent else "",
                                                           categories=existing, step="manual"))
            self._seen[entry_id] = 3
            return "manual"
        plan = effective_plan(self.store, team, day)
        if plan and plan.get("answers", {}).get("pending") == "leave" and plan.get("confirmed_at") \
                and mail.get("received", "") and mail["received"] < plan["confirmed_at"]:
            self._seen[entry_id] = 3        # arrived before the confirmation: left for manual sharing
            return "left"
        ctx = self._context(team, day, plan)
        decision = engine.decide(mail, ctx)
        if decision.step == "wait":
            return "wait"
        try:
            new_id = self.mailbox.apply(entry_id, decision.categories, (), decision.folder)
        except Exception as exc:  # noqa: BLE001
            self._seen[entry_id] = self._seen.get(entry_id, 0) + 1
            self.counts["error"] += 1
            self.store.journal_append(day, self._entry(mail, entry_id, "error", decision=decision, error=str(exc)))
            LOG.warning("Could not apply decision to %s: %s", mail.get("subject"), exc)
            return "error"
        if decision.rotation_key:
            rotation = self.store.rotation(day)
            rotation[decision.rotation_key] = decision.rotation_next
            self.store.save_rotation(day, rotation)
        self._seen[new_id] = 3
        self._seen[entry_id] = 3
        self.counts["ok"] += 1
        self.store.journal_append(day, self._entry(mail, new_id, "ok", decision=decision))
        self.store.forget_thread_cache()
        return "ok"

    @staticmethod
    def _entry(mail: dict, entry_id: str, status: str, decision: engine.Decision | None = None, **extra) -> dict:
        e = {
            "at": now_iso(), "id": entry_id, "conv": mail.get("conversation_id", ""),
            "subject": (mail.get("subject") or "")[:200], "from": mail.get("sender_email") or mail.get("sender_name", ""),
            "received": mail.get("received", ""), "importance": mail.get("importance", "normal"),
            "status": status, "pc": pc_name(),
        }
        if decision is not None:
            e.update(step=decision.step, agent=decision.agent_id, intended=decision.intended_agent_id,
                     categories=decision.categories, folder=decision.folder, rule=decision.rule_id,
                     trace=decision.trace)
        e.update(extra)
        return e

    # ── commands (run on the engine thread through call()) ──────────────
    def reassign(self, absent_ids: list[str], option: str) -> int:
        """After a regeneration: mails assigned today to agents now absent go to backup / rotation / fallback."""
        def run(mailbox):
            if option == "keep" or not absent_ids:
                return 0
            team = self.store.team()
            day = date.today()
            plan = effective_plan(self.store, team, day)
            agents, _ = self.store.agents()
            by_id = {a["id"]: a for a in agents}
            done, latest = 0, {}
            for e in self.store.journal(day):
                if e.get("status") in ("ok", "reassigned") and e.get("id"):
                    latest[e["id"]] = e
            for entry_id, e in latest.items():
                old = e.get("agent")
                if old not in absent_ids or old not in by_id:
                    continue
                mail = mailbox.read(entry_id)
                if mail is None or by_id[old]["category"].lower() not in (c.lower() for c in mail.get("categories", [])) \
                        and team["mode"] == "category":
                    continue        # changed by hand meanwhile
                ctx = self._context(team, day, plan)
                d = engine.Decision()
                target = ""
                if option == "backup":
                    for b in engine.backup_chain(ctx, old):
                        if engine.day_state(ctx, b)["state"] == model.ROTATION:
                            target = b
                            break
                if option == "rotation" or (option == "backup" and not target):
                    if engine._rotation(ctx, d):  # noqa: SLF001
                        target = d.agent_id
                if target:
                    d.agent_id, d.step = target, "reassigned"
                    engine._finish_agent(ctx, d)  # noqa: SLF001
                else:
                    engine._fallback(ctx, d)  # noqa: SLF001
                new_id = mailbox.apply(entry_id, d.categories, [by_id[old]["category"]], d.folder)
                if d.rotation_key:
                    rot = self.store.rotation(day)
                    rot[d.rotation_key] = d.rotation_next
                    self.store.save_rotation(day, rot)
                self.store.journal_append(day, self._entry(mail, new_id, "reassigned", decision=d, previous=old))
                done += 1
            return done
        return self.call(run, timeout=300)

    def send_report(self, regenerated: bool = False) -> dict:
        team = self.store.team()
        plan = self.store.plan(date.today())
        if not plan:
            raise MailboxError("no_plan")
        agents, _ = self.store.agents()
        rules, _ = self.store.rules()
        rep = report.build(team, agents, rules, plan, regenerated)
        channel = team["report"]["channel"]
        if channel == "email":
            self.call(lambda mb: delivery.send(team, rep, mb))
        elif channel == "webhook":
            delivery.send(team, rep)
        return {"channel": channel, "report": rep}
