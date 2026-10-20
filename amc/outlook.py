"""Classic Outlook for Windows, through its object model (COM, pywin32).

Works with the shared mailbox as it appears in the user's Outlook profile
(added automatically or with File > Account settings). Every method must be
called from the thread that called `open()` (COM apartment rules); the
engine worker makes sure of that.

The new Outlook for Windows has no COM object model: this module needs the
classic Outlook (supported by Microsoft until at least 2029).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from .mailbox import MailboxError

LOG = logging.getLogger("automailcat.outlook")

try:  # Windows only
    import pythoncom  # type: ignore
    import pywintypes  # type: ignore
    import win32com.client  # type: ignore
    AVAILABLE = True
except Exception:  # noqa: BLE001
    AVAILABLE = False

OL_FOLDER_INBOX = 6
OL_MAIL_ITEM = 43
MAX_BODY = 200_000
MAX_THREAD_ITEMS = 60
PR_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"


def _list_separator() -> str:
    """Outlook joins categories with the Windows list separator (", " or "; ")."""
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as key:
            sep = winreg.QueryValueEx(key, "sList")[0] or ","
    except Exception:  # noqa: BLE001
        sep = ","
    return sep


def split_categories(value: str | None) -> list[str]:
    if not value:
        return []
    for sep in (";", ","):
        value = value.replace(sep, "\x00")
    return [c.strip() for c in value.split("\x00") if c.strip()]


def _naive(dt) -> str:
    """pywin32 returns local times marked as UTC: drop the zone and keep the clock time."""
    try:
        return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second).isoformat()
    except Exception:  # noqa: BLE001
        return ""


class _ItemsEvents:
    """Receives Items.ItemAdd for the source folder."""
    queue: list | None = None
    lock: threading.Lock | None = None

    def OnItemAdd(self, item):  # noqa: N802 (COM name)
        try:
            entry_id = item.EntryID
        except Exception:  # noqa: BLE001
            return
        if self.queue is not None and self.lock is not None:
            with self.lock:
                self.queue.append(entry_id)


class OutlookMailbox:
    is_demo = False

    def __init__(self, mailbox: str, source_folder: str = "", start_outlook: bool = False):
        self.mailbox_name = mailbox.strip()
        self.source_name = source_folder.strip()
        self.start_outlook = start_outlook
        self.app = self.ns = self.store = self.inbox = self.source = None
        self._items = self._events = None
        self._queue: list[str] = []
        self._lock = threading.Lock()
        self._sep = ","

    # ── connection ──────────────────────────────────────────────────────
    def open(self):
        if not AVAILABLE:
            raise MailboxError("pywin32_missing")
        pythoncom.CoInitialize()
        try:
            self.app = win32com.client.GetActiveObject("Outlook.Application")
        except pywintypes.com_error:
            if not self.start_outlook:
                raise MailboxError("outlook_not_running")
            self.app = win32com.client.Dispatch("Outlook.Application")
        self.ns = self.app.GetNamespace("MAPI")
        self._sep = _list_separator()
        self.inbox, self.store = self._find_inbox()
        self.source = self.resolve_folder(self.source_name) if self.source_name else self.inbox
        if self.source is None:
            raise MailboxError("source_folder_not_found")
        self._items = self.source.Items
        self._events = win32com.client.WithEvents(self._items, _ItemsEvents)
        self._events.queue = self._queue
        self._events.lock = self._lock
        LOG.info("Connected to %s / %s", self.mailbox_name, self.source.FolderPath)

    def close(self):
        self._events = self._items = None
        self.source = self.inbox = self.store = self.ns = self.app = None
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass

    def status(self) -> str:
        return "connected" if self.source is not None else "closed"

    def _find_inbox(self):
        wanted = self.mailbox_name.lower()
        if not wanted:
            raise MailboxError("mailbox_missing")
        for store in self.ns.Stores:
            try:
                names = {str(store.DisplayName).lower()}
                try:
                    names.add(str(store.GetRootFolder().Name).lower())
                except Exception:  # noqa: BLE001
                    pass
                if wanted in names:
                    return store.GetDefaultFolder(OL_FOLDER_INBOX), store
            except Exception:  # noqa: BLE001
                continue
        # not in the profile as a separate store: open it as another user's Inbox
        try:
            recipient = self.ns.CreateRecipient(self.mailbox_name)
            recipient.Resolve()
            if recipient.Resolved:
                inbox = self.ns.GetSharedDefaultFolder(recipient, OL_FOLDER_INBOX)
                return inbox, inbox.Store
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Shared Inbox lookup failed: %s", exc)
        raise MailboxError("mailbox_not_found")

    # ── folders ─────────────────────────────────────────────────────────
    def resolve_folder(self, path: str):
        """'Agents/Ana' = under the Inbox; '/Archive/2026' = under the mailbox root."""
        path = (path or "").replace("\\", "/").strip()
        if not path:
            return self.inbox
        if path.startswith("/"):
            folder = self.store.GetRootFolder()
        else:
            folder = self.inbox
        for part in [p for p in path.strip("/").split("/") if p]:
            nxt = None
            for f in folder.Folders:
                if str(f.Name).strip().lower() == part.strip().lower():
                    nxt = f
                    break
            if nxt is None:
                return None
            folder = nxt
        return folder

    def folders(self) -> list[str]:
        out: list[str] = []

        def walk(folder, prefix, depth):
            if depth > 6 or len(out) > 800:
                return
            for f in folder.Folders:
                name = str(f.Name)
                path = f"{prefix}{name}"
                out.append(path)
                walk(f, path + "/", depth + 1)

        walk(self.inbox, "", 0)
        root = self.store.GetRootFolder()
        inbox_id = self.inbox.EntryID
        for f in root.Folders:
            if f.EntryID != inbox_id and int(getattr(f, "DefaultItemType", 0)) == 0:
                out.append("/" + str(f.Name))
                walk(f, "/" + str(f.Name) + "/", 1)
        return out

    # ── events and scanning ─────────────────────────────────────────────
    def pump(self, seconds: float):
        end = datetime.now().timestamp() + seconds
        while datetime.now().timestamp() < end:
            pythoncom.PumpWaitingMessages()
            pythoncom.PumpWaitingMessages()
            threading.Event().wait(0.2)

    def take_new(self) -> list[str]:
        with self._lock:
            ids, self._queue[:] = list(self._queue), []
        return ids

    def scan(self, since: datetime) -> list[str]:
        items = self.source.Items
        items.Sort("[ReceivedTime]", True)
        ids = []
        item = items.GetFirst()
        while item is not None and len(ids) < 2000:
            try:
                received = item.ReceivedTime
                if datetime.fromisoformat(_naive(received)) < since:
                    break
                if int(item.Class) == OL_MAIL_ITEM:
                    ids.append(item.EntryID)
            except Exception:  # noqa: BLE001
                pass
            item = items.GetNext()
        return ids

    # ── reading ─────────────────────────────────────────────────────────
    def _item(self, entry_id: str):
        try:
            return self.ns.GetItemFromID(entry_id, self.store.StoreID)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _smtp(address_entry, fallback: str = "") -> str:
        try:
            if str(address_entry.Type).upper() == "EX":
                user = address_entry.GetExchangeUser()
                if user is not None:
                    return str(user.PrimarySmtpAddress)
                return str(address_entry.PropertyAccessor.GetProperty(PR_SMTP))
        except Exception:  # noqa: BLE001
            pass
        return fallback

    def read(self, entry_id: str) -> dict | None:
        item = self._item(entry_id)
        if item is None or int(getattr(item, "Class", 0)) != OL_MAIL_ITEM:
            return None
        to, cc = [], []
        try:
            for r in item.Recipients:
                person = {"name": str(r.Name), "email": self._smtp(r.AddressEntry, str(r.Address))}
                (to if int(r.Type) == 1 else cc if int(r.Type) == 2 else []).append(person)
        except Exception:  # noqa: BLE001
            pass
        try:
            sender_email = str(item.SenderEmailAddress)
            if str(item.SenderEmailType).upper() == "EX":
                sender_email = self._smtp(item.Sender, sender_email)
        except Exception:  # noqa: BLE001
            sender_email = ""
        attachments = []
        try:
            for i in range(1, item.Attachments.Count + 1):
                attachments.append(str(item.Attachments.Item(i).FileName))
        except Exception:  # noqa: BLE001
            pass
        try:
            body = str(item.Body or "")[:MAX_BODY]
        except Exception:  # noqa: BLE001
            body = ""
        return {
            "id": entry_id,
            "subject": str(item.Subject or ""),
            "body": body,
            "sender_name": str(getattr(item, "SenderName", "") or ""),
            "sender_email": sender_email,
            "to": to,
            "cc": cc,
            "attachments": attachments,
            "importance": {0: "low", 2: "high"}.get(int(item.Importance), "normal"),
            "received": _naive(item.ReceivedTime),
            "conversation_id": str(getattr(item, "ConversationID", "") or ""),
            "categories": split_categories(item.Categories),
            "folder": str(item.Parent.FolderPath),
            "thread": self._thread(item, entry_id),
        }

    def _thread(self, item, entry_id: str) -> list[dict]:
        out: list[dict] = []
        try:
            conv = item.GetConversation()
        except Exception:  # noqa: BLE001
            conv = None
        if conv is None:
            return out

        def visit(node, depth=0):
            if node is None or len(out) >= MAX_THREAD_ITEMS or depth > 40:
                return
            try:
                if node.EntryID != entry_id:
                    when = getattr(node, "ReceivedTime", None) or getattr(node, "SentOn", None)
                    out.append({"categories": split_categories(getattr(node, "Categories", "")),
                                "folder": str(node.Parent.FolderPath), "time": _naive(when) if when else ""})
            except Exception:  # noqa: BLE001
                pass
            try:
                for child in conv.GetChildren(node):
                    visit(child, depth + 1)
            except Exception:  # noqa: BLE001
                pass

        try:
            for root in conv.GetRootItems():
                visit(root)
        except Exception:  # noqa: BLE001
            pass
        return out

    # ── changing ────────────────────────────────────────────────────────
    def apply(self, entry_id: str, add, remove=(), folder: str = "") -> str:
        item = self._item(entry_id)
        if item is None:
            raise MailboxError("mail_not_found")
        lowered = {r.lower() for r in remove}
        cats = [c for c in split_categories(item.Categories) if c.lower() not in lowered]
        for c in add:
            if c and c.lower() not in (x.lower() for x in cats):
                cats.append(c)
        sep = self._sep if self._sep in (",", ";") else ","
        item.Categories = f"{sep} ".join(cats)
        item.Save()
        if folder:
            target = self.resolve_folder(folder)
            if target is None:
                raise MailboxError("folder_not_found:" + folder)
            if target.EntryID != item.Parent.EntryID:
                moved = item.Move(target)
                return str(moved.EntryID)
        return entry_id

    def ensure_categories(self, names) -> list[str]:
        try:
            master = self.store.Categories
        except Exception:  # noqa: BLE001
            master = self.ns.Categories
        existing = {str(c.Name).lower() for c in master}
        added = []
        for i, name in enumerate(names):
            if name and name.lower() not in existing:
                master.Add(name, (i % 24) + 1)
                existing.add(name.lower())
                added.append(name)
        return added

    def send_mail(self, to: str, subject: str, html_body: str):
        mail = self.app.CreateItem(0)
        mail.To = to
        mail.Subject = subject
        mail.HTMLBody = html_body
        mail.Send()
