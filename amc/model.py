"""Configuration documents and their defaults.

Every team keeps its configuration in its own folder (usually a Teams /
SharePoint folder synced on the PCs of the team leader, the stand-in and the
PC that runs the engine):

    team.json            team settings (mailbox, mode, report, options)
    agents.json          agents: name, category, folder, backups
    rules.json           keyword rules, in priority order
    plans/<date>.json    the plan of one day: who works, intervals, order
    state/<date>.json    rotation position per interval (written by the engine)
    journal/<date>.jsonl one line per processed mail
    engine.lock.json     which PC runs the engine right now

The `normalize_*` functions accept partial or older documents and always
return a complete one, so a hand-edited file never breaks the engine.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import date

# Agent states for one day
ROTATION, EXCLUDED, ABSENT = "rotation", "excluded", "absent"
STATES = (ROTATION, EXCLUDED, ABSENT)

# When an excluded agent still gets a mail that is meant for him
EXCEPTIONS = ("own_thread", "named", "to_cc", "rules", "high_importance")

MODES = ("category", "folder", "both")
WHERE = ("subject", "body", "to_cc", "from", "attachments")

TEAM_DEFAULTS = {
    "name": "",
    "language": "ro",                 # language of the daily message: ro | en
    "mailbox": "",                    # shared mailbox: display name or address, as shown in Outlook
    "source_folder": "",              # empty = Inbox of the shared mailbox
    "mode": "category",               # category | folder | both
    "fallback_category": "De verificat",
    "fallback_folder": "",
    "use_thread": True,
    "use_names": True,
    "name_requires_team": True,       # first name + last name + team name must all appear
    "team_aliases": [],               # how the team name is written in mails ("Echipa X", "Team X")
    "match_to_cc_address": True,      # an agent's address in To/CC counts as naming him
    "follow_backups_of_backups": True,
    "no_backup": "rotation",          # rotation | fallback: when nobody in the backup chain is available
    "before_confirmation": "wait",    # wait | previous_plan: mails arriving before the day is confirmed
    "outside_intervals": "nearest",   # nearest | fallback: mails arriving outside the planned intervals
    "lookback_days": 1,               # how far back the start-up sweep looks for mails without an assignment
    "sweep_minutes": 5,
    "editors": [],                    # Windows user names allowed to edit; empty = everybody
    "report": {
        "channel": "copy",            # copy | webhook | email
        "webhook_url": "",
        "email_to": "",
        "include_rules": True,
        "include_backups": True,
    },
    "engine": {
        "preferred_pc": "",           # PC name that should run the engine when it is on
        "stale_minutes": 5,           # another PC takes over after this many minutes without a heartbeat
        "start_outlook": False,
    },
    "category_colors": True,
}

AGENT_DEFAULTS = {
    "id": "",
    "first_name": "",
    "last_name": "",
    "email": "",
    "aliases": [],                    # other spellings of the full name
    "category": "",                   # Outlook category of the agent (default: "First Last")
    "folder": "",                     # folder of the agent (folder mode), relative to the Inbox
    "backups": [],                    # ordered agent ids
    "active": True,                   # still in the team (inactive agents are kept for history)
    "color": "",
}

RULE_DEFAULTS = {
    "id": "",
    "name": "",
    "enabled": True,
    "all": [],                        # every term must appear
    "any": [],                        # at least one term must appear (if any are given)
    "none": [],                       # none of these may appear
    "from": [],                       # sender address / domain / name contains one of these
    "where": list(WHERE),
    "high_only": False,
    "assign": "",                     # "" = nobody (only categories / folder) | "rotation" | "agent:<id>"
    "categories": [],
    "folder": "",
    "stop": True,                     # stop evaluating after this rule (forced for assigning rules)
    "note": "",
}

PLAN_DEFAULTS = {
    "date": "",
    "confirmed": False,
    "confirmed_by": "",
    "confirmed_at": "",
    "agents": {},                     # id -> {"state", "reason", "exceptions": []}
    "intervals": [],                  # [{"start": "08:00", "end": "12:00", "order": [ids]}]
    "answers": {},                    # answers given in the morning / regenerate wizard
    "history": [],                    # [{"at", "by", "what"}]
}

AGENT_DAY_DEFAULTS = {"state": ABSENT, "reason": "", "exceptions": []}

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _merge(defaults: dict, doc: dict | None) -> dict:
    out = copy.deepcopy(defaults)
    for key, value in (doc or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _list(value) -> list[str]:
    from .textmatch import split_terms
    return split_terms(value)


def _choice(value, allowed, default):
    return value if value in allowed else default


def normalize_team(doc: dict | None) -> dict:
    t = _merge(TEAM_DEFAULTS, doc)
    t["mode"] = _choice(t["mode"], MODES, "category")
    t["language"] = _choice(t["language"], ("ro", "en"), "ro")
    t["no_backup"] = _choice(t["no_backup"], ("rotation", "fallback"), "rotation")
    t["before_confirmation"] = _choice(t["before_confirmation"], ("wait", "previous_plan"), "wait")
    t["outside_intervals"] = _choice(t["outside_intervals"], ("nearest", "fallback"), "nearest")
    t["report"]["channel"] = _choice(t["report"]["channel"], ("copy", "webhook", "email"), "copy")
    t["team_aliases"] = _list(t["team_aliases"])
    t["editors"] = _list(t["editors"])
    if not t["team_aliases"] and t["name"]:
        t["team_aliases"] = [t["name"]]
    try:
        t["lookback_days"] = max(0, min(14, int(t["lookback_days"])))
        t["sweep_minutes"] = max(1, min(60, int(t["sweep_minutes"])))
        t["engine"]["stale_minutes"] = max(1, min(120, int(t["engine"]["stale_minutes"])))
    except (TypeError, ValueError):
        t["lookback_days"], t["sweep_minutes"] = 1, 5
        t["engine"]["stale_minutes"] = 5
    return t


def full_name(agent: dict) -> str:
    return f"{agent.get('first_name', '').strip()} {agent.get('last_name', '').strip()}".strip()


def normalize_agent(doc: dict | None) -> dict:
    a = _merge(AGENT_DEFAULTS, doc)
    a["id"] = str(a["id"] or new_id())
    a["aliases"] = _list(a["aliases"])
    a["backups"] = [str(b) for b in (a["backups"] or []) if str(b) and str(b) != a["id"]]
    a["category"] = (a["category"] or full_name(a)).strip()
    a["email"] = (a["email"] or "").strip()
    return a


def normalize_agents(doc) -> list[dict]:
    items = doc.get("agents", []) if isinstance(doc, dict) else (doc or [])
    seen, out = set(), []
    for raw in items:
        a = normalize_agent(raw)
        if a["id"] in seen:
            a["id"] = new_id()
        seen.add(a["id"])
        out.append(a)
    return out


def normalize_rule(doc: dict | None) -> dict:
    r = _merge(RULE_DEFAULTS, doc)
    r["id"] = str(r["id"] or new_id())
    for key in ("all", "any", "none", "from", "categories"):
        r[key] = _list(r[key])
    r["where"] = [w for w in (r["where"] or []) if w in WHERE] or list(WHERE)
    assign = str(r["assign"] or "")
    if assign not in ("", "rotation") and not assign.startswith("agent:"):
        assign = ""
    r["assign"] = assign
    if assign:
        r["stop"] = True
    r["stop"] = bool(r["stop"])
    r["enabled"] = bool(r["enabled"])
    return r


def normalize_rules(doc) -> list[dict]:
    items = doc.get("rules", []) if isinstance(doc, dict) else (doc or [])
    return [normalize_rule(r) for r in items]


def valid_hhmm(value: str) -> bool:
    return bool(_HHMM.match(str(value or "")))


def hhmm_minutes(value: str) -> int:
    m = _HHMM.match(str(value))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def normalize_plan(doc: dict | None, day: date | None = None) -> dict:
    p = _merge(PLAN_DEFAULTS, doc)
    if day is not None:
        p["date"] = day.isoformat()
    agents = {}
    for agent_id, info in (p["agents"] or {}).items():
        d = _merge(AGENT_DAY_DEFAULTS, info if isinstance(info, dict) else {"state": info})
        d["state"] = _choice(d["state"], STATES, ABSENT)
        d["exceptions"] = [e for e in (d["exceptions"] or []) if e in EXCEPTIONS]
        agents[str(agent_id)] = d
    p["agents"] = agents
    intervals = []
    for iv in p["intervals"] or []:
        if not isinstance(iv, dict):
            continue
        start, end = iv.get("start", ""), iv.get("end", "")
        if not (valid_hhmm(start) and valid_hhmm(end)) or hhmm_minutes(end) <= hhmm_minutes(start):
            continue
        order = []
        for a in iv.get("order", []) or []:
            if str(a) not in order:
                order.append(str(a))
        intervals.append({"start": start, "end": end, "order": order})
    intervals.sort(key=lambda iv: hhmm_minutes(iv["start"]))
    p["intervals"] = intervals
    return p


def interval_key(iv: dict) -> str:
    return f"{iv['start']}-{iv['end']}"


def plan_from_previous(previous: dict, day: date) -> dict:
    """Copy of an earlier plan for a new day (not confirmed, no history)."""
    p = normalize_plan(copy.deepcopy(previous), day)
    p.update(confirmed=False, confirmed_by="", confirmed_at="", answers={}, history=[])
    return p


def empty_plan(agents: list[dict], day: date) -> dict:
    """Everybody active in rotation, one interval for the whole working day."""
    ids = [a["id"] for a in agents if a.get("active", True)]
    return normalize_plan({
        "agents": {i: {"state": ROTATION} for i in ids},
        "intervals": [{"start": "08:00", "end": "17:00", "order": ids}],
    }, day)
