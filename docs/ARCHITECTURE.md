# Architecture

```
start.bat ─► automailcat.py ─► App (amc/app.py)
                                 ├─ Server (amc/server.py)   127.0.0.1:8767, JSON API + web/ UI
                                 ├─ Tray (amc/tray.py)       pystray, skipped when DevPilot owns "tray"
                                 └─ TeamWorker per team (amc/worker.py)
                                      ├─ OutlookMailbox (amc/outlook.py)  classic Outlook via COM
                                      │  or DemoMailbox (amc/mailbox.py)  JSON file, no Outlook
                                      ├─ engine.decide() (amc/engine.py)  pure decision logic
                                      └─ TeamStore (amc/store.py)         files in the team folder
```

## Team folder (shared, synced via Teams/SharePoint)

| File | Written by | Content |
|---|---|---|
| `team.json` | UI | mailbox, mode, logic switches, report channel, engine options, editors |
| `agents.json` | UI | agents: name, e-mail, category, folder, backups, aliases |
| `rules.json` | UI | keyword rules in priority order |
| `plans/<date>.json` | UI | day plan: agent states, intervals with order, wizard answers, history |
| `state/<date>.json` | engine | rotation position per interval |
| `journal/<date>.jsonl` | engine | one line per processed mail, with the decision trace |
| `engine.lock.json` | engine | which PC/instance runs the engine, heartbeat |

Versioned writes (`_rev`) raise a conflict instead of silently overwriting a colleague's change. Writes are atomic (temp file + rename) and retried while a sync client holds the file.

## Decision (amc/engine.py)

`decide(mail, Context) -> Decision`. Order: information rules → conversation owner → agent named (To/CC address, or first + last name + team alias) → keyword rules (first match) → rotation of the current interval → fallback category. Availability per day state (`rotation`, `excluded` with exceptions, `absent`); unavailable targets follow the backup chain (optionally backups of backups), then rotation or fallback. Every step appends to `trace`, which the journal and the rule tester show.

Text matching (amc/textmatch.py): case and diacritics insensitive, whole words, trailing `*` wildcard, phrases.

## Engine (amc/worker.py)

- Leader election through `engine.lock.json`: 30 s heartbeat; takeover when the heartbeat is older than `stale_minutes` or when the team's preferred PC starts.
- New mails: Outlook `Items.ItemAdd` events, plus a sweep at start-up, after confirmation and every `sweep_minutes` (catches mails missed while no PC ran).
- Mails that already carry an agent or fallback category are left alone (manual changes win) and logged as `manual`.
- All COM calls happen on the worker thread; the UI sends work through `TeamWorker.call()`.

## Outlook (amc/outlook.py)

`GetActiveObject("Outlook.Application")`, store lookup by display name (fallback: `GetSharedDefaultFolder`), Exchange addresses resolved to SMTP, conversation via `MailItem.GetConversation()`, categories joined with the Windows list separator, `Move()` for folder mode, `Store.Categories.Add()` for missing categories, `CreateItem(0).Send()` for the e-mail report.

## DevPilot

`DEVPILOT_MANAGED` / `DEVPILOT_SUPPRESS` are read in amc/system.py: `tray` hides the tray icon, `autostart` disables the Startup entry, `keepawake` disables `SetThreadExecutionState`. `devpilot.tool.json` lists the hub options; `--action sweep|pause|resume|report|quit` forwards to the running instance over the local API.

## Security

The server binds to 127.0.0.1 only. Mutating requests require the `X-AutoMailCAT: 1` header (blocks cross-site form posts). Editing can be limited to listed Windows users per team.
