"""Local web server (127.0.0.1 only): JSON API under /api and the interface from /web.

Standard library only. Requests that change something must carry the header
`X-AutoMailCAT: 1`; browsers do not send custom headers to another site
without permission, so other web pages cannot change anything here.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import threading
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import engine, model, report, system
from .app import App
from .mailbox import DemoMailbox, MailboxError
from .store import Conflict, now_iso, user_name
from .worker import effective_plan

LOG = logging.getLogger("automailcat.server")
MAX_BODY = 2 * 1024 * 1024

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")


class ApiError(Exception):
    def __init__(self, status: int, code: str, extra: dict | None = None):
        super().__init__(code)
        self.status, self.code, self.extra = status, code, extra or {}


def _day(q: dict) -> date:
    value = (q.get("date") or [""])[0]
    try:
        return date.fromisoformat(value) if value else date.today()
    except ValueError:
        raise ApiError(400, "bad_date")


class Handler(BaseHTTPRequestHandler):
    app: App = None  # type: ignore[assignment]
    server_version = "AutoMailCAT"

    def log_message(self, fmt, *args):  # quiet
        LOG.debug(fmt, *args)

    # ── plumbing ────────────────────────────────────────────────────────
    def _send(self, status: int, payload, content_type="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "too_large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            raise ApiError(400, "bad_json")
        return data if isinstance(data, dict) else {}

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str):
        url = urlparse(self.path)
        path = unquote(url.path)
        try:
            if path.startswith("/api/"):
                if method != "GET" and self.headers.get("X-AutoMailCAT") != "1":
                    raise ApiError(403, "missing_header")
                q = parse_qs(url.query)
                body = self._body() if method in ("POST", "PUT") else {}
                fn = ROUTES.get((method, path))
                if not fn:
                    raise ApiError(404, "not_found")
                self._send(200, fn(self, q, body) or {"ok": True})
            elif method == "GET":
                self._static(path)
            else:
                raise ApiError(405, "method")
        except ApiError as exc:
            self._send(exc.status, {"error": exc.code, **exc.extra})
        except Conflict as exc:
            self._send(409, {"error": "conflict", "file": str(exc)})
        except KeyError as exc:
            self._send(404, {"error": str(exc).strip("'")})
        except (MailboxError, ValueError, TimeoutError) as exc:
            self._send(400, {"error": str(exc) or exc.__class__.__name__})
        except Exception as exc:  # noqa: BLE001
            LOG.exception("API error on %s", path)
            self._send(500, {"error": "internal", "detail": str(exc)})

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        root = self.app.web_dir.resolve()
        target = (root / path.lstrip("/")).resolve()
        if root not in target.parents and target != root or not target.is_file():
            target = root / "index.html"
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ── helpers ─────────────────────────────────────────────────────────
    def _tid(self, q: dict) -> str:
        tid = (q.get("t") or [""])[0]
        if not tid:
            raise ApiError(400, "team_required")
        return tid

    def _editable(self, store):
        team = store.team()
        if not self.app.can_edit(team):
            raise ApiError(403, "read_only")
        return team


# ── routes ──────────────────────────────────────────────────────────────

def r_status(h: Handler, q, b):
    return h.app.info()


def r_settings(h: Handler, q, b):
    changes = {k: b[k] for k in ("language", "open_browser_on_start", "keep_awake", "port") if k in b}
    if "port" in changes:
        changes["port"] = max(1024, min(65000, int(changes["port"])))
    h.app.settings.update(changes)
    if "autostart" in b:
        system.set_autostart(bool(b["autostart"]), h.app.app_dir)
    return h.app.info()


def r_pick_folder(h: Handler, q, b):
    return {"folder": system.pick_folder(b.get("title", ""))}


def r_team_add(h: Handler, q, b):
    folder = (b.get("folder") or "").strip()
    if not folder:
        raise ApiError(400, "folder_required")
    return h.app.add_team(folder, (b.get("name") or "").strip(), (b.get("mailbox") or "").strip(), b.get("language", "ro"))


def r_team_remove(h: Handler, q, b):
    h.app.remove_team(h._tid(q))


def r_team_get(h: Handler, q, b):
    tid = h._tid(q)
    store = h.app.store(tid)
    if not store.exists():
        raise ApiError(404, "team_folder_unreachable", {"folder": str(store.folder)})
    team = store.team()
    agents, arev = store.agents()
    rules, rrev = store.rules()
    w = h.app.worker(tid)
    return {"team": team, "agents": agents, "agents_rev": arev, "rules": rules, "rules_rev": rrev,
            "can_edit": h.app.can_edit(team), "engine": w.status() if w else {"role": "stopped"},
            "plan_dates": store.plan_dates()[:60]}


def r_team_put(h: Handler, q, b):
    store = h.app.store(h._tid(q))
    h._editable(store)
    saved = store.save_team(b.get("team") or {}, b.get("rev"))
    return {"team": store.team(), "rev": saved["_rev"]}


def r_agents_put(h: Handler, q, b):
    store = h.app.store(h._tid(q))
    h._editable(store)
    rev = store.save_agents(b.get("agents") or [], b.get("rev"))
    agents, _ = store.agents()
    return {"agents": agents, "rev": rev}


def r_rules_put(h: Handler, q, b):
    store = h.app.store(h._tid(q))
    h._editable(store)
    rev = store.save_rules(b.get("rules") or [], b.get("rev"))
    rules, _ = store.rules()
    return {"rules": rules, "rev": rev}


def _draft_plan(store, day: date, agents) -> tuple[dict, str]:
    plan = store.plan(day)
    if plan:
        return plan, "saved"
    prev = store.previous_plan(day)
    if prev:
        p = model.plan_from_previous(prev, day)
        source = "previous:" + prev["date"]
    else:
        p, source = model.empty_plan(agents, day), "empty"
    # agents added since: absent by default
    for a in agents:
        if a.get("active", True) and a["id"] not in p["agents"]:
            p["agents"][a["id"]] = {"state": model.ABSENT, "reason": "", "exceptions": []}
    p["_rev"] = 0
    return p, source


def r_plan_get(h: Handler, q, b):
    tid = h._tid(q)
    store = h.app.store(tid)
    day = _day(q)
    team = store.team()
    agents, _ = store.agents()
    rules, _ = store.rules()
    plan, source = _draft_plan(store, day, agents)
    rotation = store.rotation(day)
    return {"plan": plan, "source": source, "report": report.build(team, agents, rules, plan),
            "rotation": rotation, "can_edit": h.app.can_edit(team)}


def r_plan_put(h: Handler, q, b):
    tid = h._tid(q)
    store = h.app.store(tid)
    team = h._editable(store)
    day = _day(q)
    plan = b.get("plan") or {}
    action = b.get("action", "save")          # save | confirm | regenerate
    answers = b.get("answers") or {}
    old = store.plan(day)
    if action in ("confirm", "regenerate"):
        plan["confirmed"] = True
        plan["confirmed_by"] = user_name()
        plan["confirmed_at"] = plan.get("confirmed_at") if action == "regenerate" and plan.get("confirmed_at") else now_iso()
    history = list((old or {}).get("history") or [])
    history.append({"at": now_iso(), "by": user_name(), "what": action, "answers": answers})
    plan["history"] = history
    plan["answers"] = {**((old or {}).get("answers") or {}), **answers}
    saved = store.save_plan(day, plan, b.get("rev", 0) if old else None)

    result: dict = {"plan": saved}
    if day == date.today() and action in ("confirm", "regenerate"):
        if answers.get("rotation") == "restart":
            store.save_rotation(day, {})
        w = h.app.worker(tid)
        if action == "regenerate" and old and w:
            newly_absent = [a for a, st in saved["agents"].items()
                            if st["state"] != model.ROTATION and old["agents"].get(a, {}).get("state") == model.ROTATION]
            option = answers.get("assigned", "keep")
            if newly_absent and option != "keep":
                try:
                    result["reassigned"] = w.reassign(newly_absent, option)
                except Exception as exc:  # noqa: BLE001
                    result["reassign_error"] = str(exc)
        if answers.get("pending", "distribute") == "distribute" and w:
            w.request_sweep()
    agents, _ = store.agents()
    rules, _ = store.rules()
    rep = report.build(team, agents, rules, saved, regenerated=action == "regenerate")
    result["report"] = rep
    if action in ("confirm", "regenerate") and answers.get("send", "yes") == "yes" and team["report"]["channel"] != "copy":
        try:
            w = h.app.worker(tid)
            if w is None:
                raise MailboxError("engine_not_running")
            result["sent"] = w.send_report(regenerated=action == "regenerate")["channel"]
        except Exception as exc:  # noqa: BLE001
            result["send_error"] = str(exc)
    return result


def r_report_send(h: Handler, q, b):
    w = h.app.worker(h._tid(q))
    if w is None:
        raise ApiError(400, "engine_not_running")
    return w.send_report(regenerated=bool(b.get("regenerated")))


def r_report_preview(h: Handler, q, b):
    store = h.app.store(h._tid(q))
    team = store.team()
    if isinstance(b.get("team"), dict):
        team = model.normalize_team({**team, **b["team"]})
    agents, _ = store.agents()
    rules, _ = store.rules()
    plan = model.normalize_plan(b.get("plan") or {}, _day(q))
    plan["confirmed_by"] = (b.get("plan") or {}).get("confirmed_by", "")
    return {"report": report.build(team, agents, rules, plan)}


def r_journal(h: Handler, q, b):
    store = h.app.store(h._tid(q))
    day = _day(q)
    return {"entries": store.journal(day)[-2000:], "date": day.isoformat()}


def r_test(h: Handler, q, b):
    """Dry run of the decision for a mail typed in the interface (nothing is changed)."""
    store = h.app.store(h._tid(q))
    team = store.team()
    if isinstance(b.get("team"), dict):
        team = model.normalize_team({**team, **b["team"]})
    agents = model.normalize_agents(b["agents"]) if isinstance(b.get("agents"), list) else store.agents()[0]
    rules = model.normalize_rules(b["rules"]) if isinstance(b.get("rules"), list) else store.rules()[0]
    day = date.today()
    plan = b.get("plan")
    plan = model.normalize_plan(plan, day) if isinstance(plan, dict) else effective_plan(store, team, day)
    if plan is not None and b.get("ignore_confirmation", True):
        plan = dict(plan, confirmed=True)
    mail = dict(b.get("mail") or {})
    for key in ("to", "cc"):
        if isinstance(mail.get(key), str):
            mail[key] = [{"name": x.strip(), "email": x.strip() if "@" in x else ""}
                         for x in mail[key].replace(";", ",").split(",") if x.strip()]
    if isinstance(mail.get("attachments"), str):
        mail["attachments"] = [x.strip() for x in mail["attachments"].replace(";", ",").split(",") if x.strip()]
    thread_cat = (mail.pop("thread_category", "") or "").strip()
    if thread_cat:
        mail["thread"] = [{"categories": [thread_cat], "time": "0"}]
    now = datetime.now()
    if b.get("time") and model.valid_hhmm(b["time"]):
        hh, mm = b["time"].split(":")
        now = now.replace(hour=int(hh), minute=int(mm))
    ctx = engine.Context(team=team, agents=agents, rules=rules, plan=plan, rotation=store.rotation(day),
                         thread_owners={}, now=now)
    return {"decision": engine.decide(mail, ctx).as_dict()}


def r_folders(h: Handler, q, b):
    w = h.app.worker(h._tid(q))
    if w is None:
        raise ApiError(400, "engine_not_running")
    return {"folders": w.call(lambda mb: mb.folders())}


def r_categories(h: Handler, q, b):
    tid = h._tid(q)
    store = h.app.store(tid)
    team = store.team()
    agents, _ = store.agents()
    rules, _ = store.rules()
    names = [a["category"] for a in agents if a.get("active", True)] + [team["fallback_category"]]
    for r in rules:
        names += r["categories"]
    w = h.app.worker(tid)
    if w is None:
        raise ApiError(400, "engine_not_running")
    return {"added": w.call(lambda mb: mb.ensure_categories(list(dict.fromkeys(names))))}


def r_engine(h: Handler, q, b):
    tid = h._tid(q)
    w = h.app.worker(tid)
    action = b.get("action")
    if action in ("enable", "disable"):
        h.app.set_engine_enabled(tid, action == "enable")
    elif w is None:
        raise ApiError(400, "engine_not_running")
    elif action == "pause":
        w.paused = True
    elif action == "resume":
        w.paused = False
        w.request_sweep()
    elif action == "sweep":
        w.request_sweep()
    elif action == "reconnect":
        w.reconnect_requested = True
    return {"engine": (h.app.worker(tid) or w).status() if (h.app.worker(tid) or w) else {}}


def r_action(h: Handler, q, b):
    """Actions sent by `automailcat.py --action …` (also used by DevPilot)."""
    action = b.get("action", "")
    teams = h.app.teams()
    if b.get("team"):
        teams = [t for t in teams if t["id"] == b["team"] or t["name"].lower() == str(b["team"]).lower()]
    for t in teams:
        w = h.app.worker(t["id"])
        if not w:
            continue
        if action == "sweep":
            w.request_sweep()
        elif action == "pause":
            w.paused = True
        elif action == "resume":
            w.paused = False
            w.request_sweep()
        elif action == "report":
            try:
                w.send_report()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("report for %s: %s", t["name"], exc)
    if action == "quit" and h.app.on_quit:
        threading.Timer(0.3, h.app.on_quit).start()
    return {"ok": True}


def _demo_box(h: Handler, q) -> DemoMailbox:
    entry = h.app.team_entry(h._tid(q))
    if not (entry.get("demo") or h.app.demo):
        raise ApiError(400, "not_demo")
    return DemoMailbox(entry["folder"])


def r_demo_mails(h: Handler, q, b):
    return {"mails": _demo_box(h, q).mails()[-200:]}


def r_demo_add(h: Handler, q, b):
    box = _demo_box(h, q)
    mail = dict(b.get("mail") or {})
    for key in ("to", "cc"):
        if isinstance(mail.get(key), str):
            mail[key] = [{"name": x.strip(), "email": x.strip() if "@" in x else ""}
                         for x in mail[key].replace(";", ",").split(",") if x.strip()]
    if isinstance(mail.get("attachments"), str):
        mail["attachments"] = [x.strip() for x in mail["attachments"].split(",") if x.strip()]
    entry_id = box.add_mail(mail)
    w = h.app.worker(h._tid(q))
    if w and w.mailbox is not None and getattr(w.mailbox, "is_demo", False):
        w.mailbox._new.append(entry_id)  # noqa: SLF001  (wake the running engine)
        w.mailbox._event.set()  # noqa: SLF001
    return {"id": entry_id}


def r_demo_seed(h: Handler, q, b):
    box = _demo_box(h, q)
    ids = box.seed(int(b.get("count", 6)))
    w = h.app.worker(h._tid(q))
    if w:
        w.request_sweep()
    return {"ids": ids}


def r_demo_clear(h: Handler, q, b):
    _demo_box(h, q).clear()


def r_log(h: Handler, q, b):
    path = h.app.log_path
    if not path or not Path(path).exists():
        return {"lines": []}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    return {"lines": lines}


ROUTES = {
    ("GET", "/api/status"): r_status,
    ("POST", "/api/settings"): r_settings,
    ("POST", "/api/pick-folder"): r_pick_folder,
    ("POST", "/api/teams/add"): r_team_add,
    ("POST", "/api/teams/remove"): r_team_remove,
    ("GET", "/api/team"): r_team_get,
    ("PUT", "/api/team"): r_team_put,
    ("PUT", "/api/agents"): r_agents_put,
    ("PUT", "/api/rules"): r_rules_put,
    ("GET", "/api/plan"): r_plan_get,
    ("PUT", "/api/plan"): r_plan_put,
    ("POST", "/api/report/send"): r_report_send,
    ("POST", "/api/report/preview"): r_report_preview,
    ("GET", "/api/journal"): r_journal,
    ("POST", "/api/test"): r_test,
    ("GET", "/api/folders"): r_folders,
    ("POST", "/api/categories"): r_categories,
    ("POST", "/api/engine"): r_engine,
    ("POST", "/api/action"): r_action,
    ("GET", "/api/demo/mails"): r_demo_mails,
    ("POST", "/api/demo/mail"): r_demo_add,
    ("POST", "/api/demo/seed"): r_demo_seed,
    ("POST", "/api/demo/clear"): r_demo_clear,
    ("GET", "/api/log"): r_log,
}


class Server:
    def __init__(self, app: App, port: int):
        handler = type("BoundHandler", (Handler,), {"app": app})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{port}/"
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="http", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
