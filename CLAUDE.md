# AutoMailCAT – notes for Claude

- Python 3.10+, standard library only plus `pywin32` (Outlook COM) and optional `pystray` + `Pillow`. No `.exe` builds: the app is started from `start.bat` (antivirus blocks Python executables).
- Classic Outlook only. All COM calls stay on the `TeamWorker` thread (`amc/worker.py`).
- Decision logic lives in `amc/engine.py` and must stay free of Outlook/IO so it can be unit tested and used by the rule tester.
- UI: plain JavaScript in `web/` (no build step, no CDN). Every text goes through `web/js/i18n.js` in Romanian and English.
- README and docs: never mention the employer's name, company e-mail addresses, internal user IDs or internal numbers. Use `example.test` addresses in examples.
- Users are non-technical: settings are chosen in the interface (drop-downs, checkboxes), never by editing JSON.
- Code, comments and commit messages in English; replies to the user in Romanian.
- Tests: `python -m unittest discover -s tests -t .`; manual run without Outlook: `python automailcat.py --demo --no-tray`.

## Shared context
Project overview and open bugs/changes live in two Google Docs: **PROIECTE_CONTEXT (live)** and **MODIFICARI_PROIECTE (live)** — read only the AutoMailCAT section. Remove items from MODIFICARI once implemented and confirmed.

## Keep this file current
Update it in the same commit when: install/test/run commands change, a module is added/moved, the DevPilot integration changes, or a bug teaches a rule worth remembering. Not for ordinary features. Keep it under ~60 lines.
