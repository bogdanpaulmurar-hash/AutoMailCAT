"""The decision: who gets a mail, which categories it gets and where it goes.

Pure logic, no Outlook: the same code runs in the engine, in the rule tester
of the interface and in the unit tests.

Order of evaluation
  0. information rules (no assignee, "stop" off) add their categories and
     evaluation continues
  1. same conversation  -> the agent who owns the thread
  2. agent named         -> address in To/CC, or first name + last name
                            (+ team name) in subject / body / To-CC
  3. keyword rules       -> first matching rule in priority order
  4. rotation            -> next available agent of the current interval
  5. nothing possible    -> fallback category ("De verificat")

If the chosen agent is not available today, the mail follows his backup
chain; when nobody in the chain is available it goes to rotation or to the
fallback category, depending on the team setting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import textmatch as tm
from .model import (ABSENT, EXCLUDED, ROTATION, full_name, hhmm_minutes,
                    interval_key)

MAIL_FIELDS = ("subject", "body", "to_cc", "from", "attachments")


@dataclass
class Context:
    team: dict
    agents: list[dict]
    rules: list[dict]
    plan: dict | None
    rotation: dict = field(default_factory=dict)        # interval key -> next position
    thread_owners: dict = field(default_factory=dict)   # conversation id -> agent id (from the journal)
    now: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self.by_id = {a["id"]: a for a in self.agents}
        self.by_category = {a["category"].strip().lower(): a for a in self.agents if a.get("category")}


@dataclass
class Decision:
    step: str = ""                     # thread | name | rule | rotation | fallback | rule_only | wait
    agent_id: str = ""
    intended_agent_id: str = ""        # set when a backup received the mail instead
    categories: list[str] = field(default_factory=list)
    folder: str = ""
    rule_id: str = ""
    rotation_key: str = ""
    rotation_next: int | None = None
    trace: list[dict] = field(default_factory=list)

    def note(self, step: str, ok: bool | None, key: str, **params):
        self.trace.append({"step": step, "ok": ok, "key": key, "params": params})

    def add_categories(self, cats):
        for c in cats:
            c = str(c).strip()
            if c and c.lower() not in (x.lower() for x in self.categories):
                self.categories.append(c)

    def as_dict(self) -> dict:
        return {
            "step": self.step, "agent_id": self.agent_id, "intended_agent_id": self.intended_agent_id,
            "categories": self.categories, "folder": self.folder, "rule_id": self.rule_id,
            "rotation_key": self.rotation_key, "rotation_next": self.rotation_next, "trace": self.trace,
        }


# ── mail text ───────────────────────────────────────────────────────────

def _people_text(people) -> str:
    parts = []
    for p in people or []:
        if isinstance(p, dict):
            parts += [p.get("name", ""), p.get("email", "")]
        else:
            parts.append(str(p))
    return " ".join(x for x in parts if x)


def mail_texts(mail: dict) -> dict[str, str]:
    """Normalised text of every searchable part of a mail."""
    return {
        "subject": tm.normalize(mail.get("subject")),
        "body": tm.normalize(mail.get("body")),
        "to_cc": tm.normalize(_people_text(list(mail.get("to") or []) + list(mail.get("cc") or []))),
        "from": tm.normalize(f"{mail.get('sender_name', '')} {mail.get('sender_email', '')}"),
        "attachments": tm.normalize(" ".join(mail.get("attachments") or [])),
    }


def _addresses(people) -> set[str]:
    out = set()
    for p in people or []:
        email = p.get("email", "") if isinstance(p, dict) else str(p)
        if email:
            out.add(email.strip().lower())
    return out


def is_high(mail: dict) -> bool:
    return str(mail.get("importance", "")).lower() in ("high", "2")


# ── availability ────────────────────────────────────────────────────────

def day_state(ctx: Context, agent_id: str) -> dict:
    if not ctx.plan:
        return {"state": ABSENT, "reason": "", "exceptions": []}
    return ctx.plan["agents"].get(agent_id) or {"state": ABSENT, "reason": "", "exceptions": []}


def available_for(ctx: Context, agent_id: str, reason: str, high: bool) -> bool:
    """Can `agent_id` receive a mail meant for him for `reason` (own_thread / named / to_cc / rules)?"""
    agent = ctx.by_id.get(agent_id)
    if not agent or not agent.get("active", True):
        return False
    st = day_state(ctx, agent_id)
    if st["state"] == ROTATION:
        return True
    if st["state"] == EXCLUDED:
        ex = st.get("exceptions") or []
        return reason in ex or (high and "high_importance" in ex)
    return False


def backup_chain(ctx: Context, agent_id: str) -> list[str]:
    """Backups of the agent in order; with the team option on, also backups of backups (breadth first)."""
    start = ctx.by_id.get(agent_id)
    if not start:
        return []
    seen, chain = {agent_id}, []
    queue = list(start.get("backups") or [])
    while queue:
        b = queue.pop(0)
        if b in seen or b not in ctx.by_id:
            continue
        seen.add(b)
        chain.append(b)
        if ctx.team.get("follow_backups_of_backups", True):
            queue += [x for x in ctx.by_id[b].get("backups") or [] if x not in seen]
    return chain


def _route(ctx: Context, d: Decision, agent_id: str, reason: str, high: bool, step: str) -> bool:
    """Give the mail to `agent_id` or to the first available backup. False = nobody, caller decides."""
    name = full_name(ctx.by_id[agent_id]) if agent_id in ctx.by_id else agent_id
    if available_for(ctx, agent_id, reason, high):
        d.agent_id, d.step = agent_id, step
        d.note(step, True, "assigned", agent=name)
        return True
    st = day_state(ctx, agent_id)
    d.note(step, False, "not_available_" + st["state"], agent=name, reason=st.get("reason", ""))
    for b in backup_chain(ctx, agent_id):
        if day_state(ctx, b)["state"] == ROTATION and ctx.by_id[b].get("active", True):
            d.agent_id, d.intended_agent_id, d.step = b, agent_id, step
            d.note(step, True, "assigned_backup", agent=full_name(ctx.by_id[b]), of=name)
            return True
    d.note(step, False, "no_backup", agent=name)
    return False


# ── steps ───────────────────────────────────────────────────────────────

def thread_owner(ctx: Context, mail: dict) -> str:
    """Agent who owns the conversation: newest earlier mail with an agent category or in an agent folder."""
    items = sorted(mail.get("thread") or [], key=lambda x: str(x.get("time", "")), reverse=True)
    for item in items:
        for cat in item.get("categories") or []:
            a = ctx.by_category.get(str(cat).strip().lower())
            if a:
                return a["id"]
        folder = str(item.get("folder", "")).replace("\\", "/").strip("/").lower()
        if folder:
            for a in ctx.agents:
                f = str(a.get("folder", "")).replace("\\", "/").strip("/").lower()
                if f and (folder == f or folder.endswith("/" + f)):
                    return a["id"]
    conv = mail.get("conversation_id")
    if conv and conv in ctx.thread_owners and ctx.thread_owners[conv] in ctx.by_id:
        return ctx.thread_owners[conv]
    return ""


def named_agent(ctx: Context, mail: dict, texts: dict) -> tuple[str, str]:
    """(agent id, reason) for an agent addressed in To/CC or named in the text, else ("", "")."""
    sender = str(mail.get("sender_email", "")).strip().lower()
    candidates = [a for a in ctx.agents if a.get("active", True) and (a.get("email", "").lower() != sender or not sender)]
    if ctx.team.get("match_to_cc_address", True):
        addresses = _addresses(mail.get("to")) | _addresses(mail.get("cc"))
        for a in candidates:
            if a.get("email") and a["email"].lower() in addresses:
                return a["id"], "to_cc"
    team_ok = True
    if ctx.team.get("name_requires_team", True):
        aliases = ctx.team.get("team_aliases") or []
        team_ok = bool(aliases) and any(
            tm.contains(al, texts[f]) for al in aliases for f in ("subject", "body", "to_cc"))
    if not team_ok:
        return "", "team_missing"
    best, best_pos = "", None
    for a in candidates:
        first, last = a.get("first_name", "").strip(), a.get("last_name", "").strip()
        names = [n for n in (f"{first} {last}", f"{last} {first}") if first and last] + list(a.get("aliases") or [])
        for f_index, f in enumerate(("subject", "to_cc", "body")):
            for n in names:
                pos = tm.find(n, texts[f])
                if pos >= 0:
                    key = (f_index, pos)
                    if best_pos is None or key < best_pos:
                        best, best_pos = a["id"], key
    return (best, "named") if best else ("", "")


def rule_matches(rule: dict, mail: dict, texts: dict) -> bool:
    if not rule.get("enabled", True):
        return False
    if not (rule["all"] or rule["any"] or rule["from"]):
        return False                     # a rule without conditions would catch every mail
    if rule.get("high_only") and not is_high(mail):
        return False
    fields = [texts[f] for f in rule["where"]]

    def found(term):
        return any(tm.contains(term, t) for t in fields)

    if any(not found(t) for t in rule["all"]):
        return False
    if rule["any"] and not any(found(t) for t in rule["any"]):
        return False
    if any(found(t) for t in rule["none"]):
        return False
    if rule["from"]:
        sender = texts["from"]
        if not any(tm.normalize(x) and tm.normalize(x) in sender for x in rule["from"]):
            return False
    return True


def current_interval(ctx: Context) -> tuple[dict | None, str]:
    """(interval, why) for the current time; builds a whole-day interval when the plan has none."""
    plan = ctx.plan or {}
    intervals = plan.get("intervals") or []
    if not intervals:
        order = [a["id"] for a in ctx.agents if day_state(ctx, a["id"])["state"] == ROTATION]
        return {"start": "00:00", "end": "23:59", "order": order}, "whole_day"
    minute = ctx.now.hour * 60 + ctx.now.minute
    for iv in intervals:
        if hhmm_minutes(iv["start"]) <= minute < hhmm_minutes(iv["end"]):
            return iv, "inside"
    if ctx.team.get("outside_intervals") == "fallback":
        return None, "outside"
    if minute < hhmm_minutes(intervals[0]["start"]):
        return intervals[0], "before_first"
    if minute >= hhmm_minutes(intervals[-1]["end"]):
        return intervals[-1], "after_last"
    # in a gap between two intervals: the next one
    for iv in intervals:
        if minute < hhmm_minutes(iv["start"]):
            return iv, "gap"
    return intervals[-1], "after_last"


def _rotation(ctx: Context, d: Decision) -> bool:
    iv, why = current_interval(ctx)
    if iv is None:
        d.note("rotation", False, "outside_intervals")
        return False
    key = interval_key(iv)
    order = [a for a in iv["order"] if a in ctx.by_id]
    if not order:
        d.note("rotation", False, "empty_order", interval=key)
        return False
    start = int(ctx.rotation.get(key, 0)) % len(order)
    for k in range(len(order)):
        idx = (start + k) % len(order)
        aid = order[idx]
        if day_state(ctx, aid)["state"] == ROTATION and ctx.by_id[aid].get("active", True):
            d.agent_id, d.step = aid, "rotation"
            d.rotation_key, d.rotation_next = key, (idx + 1) % len(order)
            d.note("rotation", True, "rotation_pick", agent=full_name(ctx.by_id[aid]), interval=key,
                   position=idx + 1, why=why)
            return True
    d.note("rotation", False, "nobody_in_rotation", interval=key)
    return False


def _finish_agent(ctx: Context, d: Decision, rule: dict | None = None):
    agent = ctx.by_id[d.agent_id]
    mode = ctx.team.get("mode", "category")
    folder = agent.get("folder", "")
    if mode in ("category", "both") or not folder:
        d.add_categories([agent["category"]])
    if mode in ("folder", "both") and folder:
        d.folder = folder
    if rule and rule.get("folder"):          # a folder set on the rule always wins
        d.folder = rule["folder"]


def _fallback(ctx: Context, d: Decision):
    d.step = "fallback"
    d.agent_id = ""
    d.add_categories([ctx.team.get("fallback_category") or "De verificat"])
    d.folder = ctx.team.get("fallback_folder", "") or ""
    d.note("fallback", True, "fallback", category=ctx.team.get("fallback_category"))


# ── main entry ──────────────────────────────────────────────────────────

def decide(mail: dict, ctx: Context) -> Decision:
    d = Decision()
    plan = ctx.plan
    if plan is None or (not plan.get("confirmed") and ctx.team.get("before_confirmation", "wait") == "wait"):
        d.step = "wait"
        d.note("plan", None, "waiting_for_confirmation")
        return d

    texts = mail_texts(mail)
    high = is_high(mail)
    rules = [r for r in ctx.rules if r.get("enabled", True)]

    # 0. information rules
    for r in rules:
        if not r["stop"] and not r["assign"] and rule_matches(r, mail, texts):
            d.add_categories(r["categories"])
            d.note("info", True, "info_rule", rule=r["name"], categories=", ".join(r["categories"]))

    # 1. same conversation
    if ctx.team.get("use_thread", True):
        owner = thread_owner(ctx, mail)
        if owner:
            d.note("thread", True, "thread_owner", agent=full_name(ctx.by_id[owner]))
            if _route(ctx, d, owner, "own_thread", high, "thread"):
                _finish_agent(ctx, d)
                return d
            return _no_backup(ctx, d)
        d.note("thread", False, "no_thread_owner")

    # 2. agent named
    if ctx.team.get("use_names", True):
        agent_id, reason = named_agent(ctx, mail, texts)
        if agent_id:
            d.note("name", True, "named_" + reason, agent=full_name(ctx.by_id[agent_id]))
            if _route(ctx, d, agent_id, reason, high, "name"):
                _finish_agent(ctx, d)
                return d
            return _no_backup(ctx, d)
        d.note("name", False, "team_missing" if reason == "team_missing" else "nobody_named")

    # 3. keyword rules
    for r in rules:
        if not r["stop"] and not r["assign"]:
            continue
        if not rule_matches(r, mail, texts):
            continue
        d.rule_id = r["id"]
        d.add_categories(r["categories"])
        d.note("rule", True, "rule_match", rule=r["name"])
        if r["assign"].startswith("agent:"):
            target = r["assign"][6:]
            if target in ctx.by_id and _route(ctx, d, target, "rules", high, "rule"):
                _finish_agent(ctx, d, r)
                return d
            return _no_backup(ctx, d)
        if r["assign"] == "rotation":
            if _rotation(ctx, d):
                d.step = "rule"
                _finish_agent(ctx, d, r)
                return d
            _fallback(ctx, d)
            return d
        # nobody: categories / folder only
        d.step = "rule_only"
        d.folder = r.get("folder", "") or ""
        return d
    if rules:
        d.note("rule", False, "no_rule")

    # 4. rotation
    if _rotation(ctx, d):
        _finish_agent(ctx, d)
        return d
    _fallback(ctx, d)
    return d


def _no_backup(ctx: Context, d: Decision) -> Decision:
    if ctx.team.get("no_backup") == "rotation" and _rotation(ctx, d):
        _finish_agent(ctx, d)
        return d
    _fallback(ctx, d)
    return d
