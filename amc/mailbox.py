"""Mailbox access. `OutlookMailbox` (amc.outlook) talks to classic Outlook;
`DemoMailbox` keeps a small fictional mailbox in a JSON file so the whole
app can be tried, and taught, without Outlook.

Both expose the same methods; all of them are called from the engine thread.

    open() / close()
    pump(seconds)                  wait for Outlook events
    take_new() -> [entry ids]      mails that arrived since the last call
    scan(since) -> [entry ids]     mails in the source folder received since `since`
    read(entry_id) -> dict | None  the mail (see engine.mail_texts) + "categories", "folder", "thread"
    apply(entry_id, add, remove, folder) -> new entry id
    folders() -> [paths]           folder tree of the mailbox, relative to the Inbox
    ensure_categories(names)
    send_mail(to, subject, html)
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .store import read_json, write_json


class MailboxError(Exception):
    pass


DEMO_MAILS = [
    {"subject": "Factura restantă septembrie", "body": "Bună ziua, vă rog să verificați facturile restante pentru luna septembrie.",
     "sender_name": "Client Unu", "sender_email": "contact@client-unu.test"},
    {"subject": "Mentenanță planificată – downtime sâmbătă", "body": "Sistemul va fi indisponibil sâmbătă între 22:00 și 02:00.",
     "sender_name": "Echipa IT", "sender_email": "it@example.test"},
    {"subject": "Întrebare despre contract", "body": "Vă rog să mă ajutați cu o întrebare despre contract. Mulțumesc!",
     "sender_name": "Client Doi", "sender_email": "office@client-doi.test"},
    {"subject": "Pentru Dan Ionescu", "body": "Salut, vă rog să preia Dan Ionescu din Echipa Demo solicitarea de mai jos.",
     "sender_name": "Client Trei", "sender_email": "info@client-trei.test"},
    {"subject": "URGENT: acces blocat", "body": "Nu ne putem conecta. Este urgent.", "importance": "high",
     "sender_name": "Client Patru", "sender_email": "help@client-patru.test"},
    {"subject": "Newsletter octombrie", "body": "Noutățile lunii.", "sender_name": "Newsletter", "sender_email": "news@newsletter.test"},
]


class DemoMailbox:
    """A fictional shared mailbox stored in <team folder>/demo-mailbox.json."""

    is_demo = True

    def __init__(self, team_folder: Path):
        self.path = Path(team_folder) / "demo-mailbox.json"
        self._new: list[str] = []
        self._lock = threading.Lock()
        self._event = threading.Event()

    def _load(self) -> dict:
        data = read_json(self.path, None)
        if not data:
            data = {"folders": ["Agenti/Ana Pop", "Agenti/Dan Ionescu", "Agenti/Eva Muresan", "Info/Newsletter"],
                    "categories": [], "mails": [], "sent": []}
        return data

    def _save(self, data: dict):
        write_json(self.path, data)

    def open(self):
        self._load()

    def close(self):
        pass

    def status(self) -> str:
        return "demo"

    def pump(self, seconds: float):
        self._event.wait(seconds)
        self._event.clear()

    def take_new(self) -> list[str]:
        with self._lock:
            ids, self._new = self._new, []
        return ids

    def add_mail(self, mail: dict) -> str:
        """Simulates a new mail arriving in the shared Inbox."""
        with self._lock:
            data = self._load()
            m = {"id": uuid.uuid4().hex[:12], "subject": "", "body": "", "sender_name": "", "sender_email": "",
                 "to": [{"name": "Shared mailbox", "email": "shared@example.test"}], "cc": [], "attachments": [],
                 "importance": "normal", "categories": [], "folder": "", "conversation_id": uuid.uuid4().hex[:10],
                 "received": datetime.now().isoformat(timespec="seconds")}
            m.update({k: v for k, v in mail.items() if k in m and k != "id"})
            reply_to = mail.get("reply_to")
            if reply_to:
                original = next((x for x in data["mails"] if x["id"] == reply_to), None)
                if original:
                    m["conversation_id"] = original["conversation_id"]
                    if not m["subject"]:
                        m["subject"] = "RE: " + original["subject"]
            data["mails"].append(m)
            self._save(data)
            self._new.append(m["id"])
        self._event.set()
        return m["id"]

    def seed(self, count: int = 6) -> list[str]:
        return [self.add_mail(dict(DEMO_MAILS[i % len(DEMO_MAILS)])) for i in range(count)]

    def scan(self, since: datetime) -> list[str]:
        data = self._load()
        return [m["id"] for m in data["mails"]
                if m["folder"] == "" and datetime.fromisoformat(m["received"]) >= since]

    def read(self, entry_id: str) -> dict | None:
        data = self._load()
        m = next((x for x in data["mails"] if x["id"] == entry_id), None)
        if not m:
            return None
        m = dict(m)
        m["thread"] = [{"categories": x["categories"], "folder": "Inbox/" + x["folder"] if x["folder"] else "Inbox",
                        "time": x["received"]}
                       for x in data["mails"] if x["conversation_id"] == m["conversation_id"] and x["id"] != entry_id
                       and x["received"] <= m["received"]]
        return m

    def apply(self, entry_id: str, add, remove=(), folder: str = "") -> str:
        with self._lock:
            data = self._load()
            m = next((x for x in data["mails"] if x["id"] == entry_id), None)
            if not m:
                raise MailboxError("mail_not_found")
            lowered = {r.lower() for r in remove}
            cats = [c for c in m["categories"] if c.lower() not in lowered]
            for c in add:
                if c.lower() not in (x.lower() for x in cats):
                    cats.append(c)
            m["categories"] = cats
            if folder:
                clean = folder.replace("\\", "/").strip("/")
                if clean not in data["folders"]:
                    raise MailboxError("folder_not_found:" + folder)
                m["folder"] = clean
            self._save(data)
        return entry_id

    def folders(self) -> list[str]:
        return list(self._load()["folders"])

    def ensure_categories(self, names) -> list[str]:
        data = self._load()
        added = [n for n in names if n and n not in data["categories"]]
        data["categories"] += added
        self._save(data)
        return added

    def send_mail(self, to: str, subject: str, html_body: str):
        data = self._load()
        data["sent"].append({"to": to, "subject": subject, "html": html_body, "at": datetime.now().isoformat(timespec="seconds")})
        data["sent"] = data["sent"][-20:]
        self._save(data)

    def mails(self) -> list[dict]:
        return self._load()["mails"]

    def clear(self):
        data = self._load()
        data["mails"], data["sent"] = [], []
        self._save(data)


def since_for(lookback_days: int) -> datetime:
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=max(0, lookback_days - 1)) if lookback_days else datetime.now() - timedelta(hours=1)
