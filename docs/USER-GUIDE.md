# AutoMailCAT user guide

For team leaders, stand-ins and anyone setting up a team. No programming knowledge needed.

## 1. What the PC needs

- Windows with the **classic Outlook** open and the shared mailbox visible in the folder list.
- **Python 3.10 or newer** from python.org (tick *Add python.exe to PATH*).
- The team's shared folder, synced from Teams/SharePoint (channel → *Files* → *Sync*, or *Add shortcut to OneDrive*).

The engine runs on **one PC** per team. AutoMailCAT may be installed on several PCs: the others are used for setting things up and take over automatically when the main PC is switched off.

## 2. Install

1. On GitHub: **Code → Download ZIP**, unzip, e.g. into `Documents\AutoMailCAT`.
2. Double-click **install.bat**.
3. Double-click **start.bat**: the AutoMailCAT page opens in the browser and an icon (envelope with a tick) appears next to the clock. Right-click it for Open, Process now, Pause, Quit.

To try it without Outlook: **start-demo.bat** (fictional team, agents, rules and mailbox).

## 3. Setting up a team

1. **Setup → Add a team → Choose folder…**: the team's synced folder. For a new folder also give the team name and the shared mailbox. The stand-in adds the same folder on his PC.
2. **Team**: the shared mailbox (exactly as shown in Outlook), how the team name appears in mails, what happens to the mail (category, folder, both), the "to check" category, the assignment steps, who may edit.
3. **Agents**: first and last name, e-mail address, Outlook category (default "First Last"), folder (**Choose from Outlook** lists the mailbox folders), backups in order, other spellings of the name. Then **Team → Create missing categories in Outlook**.
4. **Rules**: read from top to bottom like Outlook rules; drag them into order.

| Field | Example | Meaning |
|---|---|---|
| Contains ALL words | `invoic*` and `overdue` | both must appear |
| Contains AT LEAST ONE of | `downtime`, `maintenance` | one is enough |
| Contains NONE of | `cancelled` | if present, the rule does not apply |
| Sender contains | `newsletter.test` | sender address or name |
| Who gets the mail | an agent / rotation / nobody | "nobody" = category or folder only |

Case and accents do not matter; `*` at the end matches any ending. A rule with nobody assigned and "Stop evaluating" off is an **information rule**: it adds its categories and the mail continues, so one mail can get several categories. **Test a mail** (right side) shows step by step who would get a sample mail, without changing anything.

## 4. Every morning

1. Open **Today** (the proposal is copied from the last working day).
2. For every agent: **In rotation**, **Out of rotation** (reason from the list + what he still gets) or **Absent** (his mails go to his backup).
3. **Intervals**: drag the names into order per time interval. Agents out of rotation or absent stay in the list but are skipped.
4. **Confirm the day** and answer the drop-down questions (mails that arrived before the confirmation, where the rotation starts, send the message or not).

## 5. Changes during the day

Edit (e.g. someone becomes *Absent*) and press **Regenerate**. You choose the reason, what happens to mails already assigned today to people no longer in rotation (stay / go to backup / shared again / "to check"), whether the rotation continues, and whether the message is sent again. Mails whose category was changed by hand are not moved.

## 6. Journal

Every processed mail with time, agent and the step that decided. Click a row for the full explanation.

## 7. FAQ

- **The engine PC was switched off?** Another PC running AutoMailCAT with Outlook takes over after a few minutes; otherwise the mails are processed at the next start.
- **Someone re-categorised a mail by hand?** AutoMailCAT leaves it alone; replies follow the new category.
- **Why was the named agent not chosen?** Usually only the first name was written, or the team name was missing. Rules → Test a mail shows the reason.
- **Commas in category names?** No – Outlook uses them as separators.
- **New Outlook?** Not supported; classic Outlook is required.
- **Local log and settings?** `%LOCALAPPDATA%\AutoMailCAT`. Team settings live in the team's shared folder.

## 8. DevPilot

In DevPilot: add a Python tool, pick `automailcat.py`, then **From devpilot.tool.json**. The options appear in the hub; tray icon, start with Windows and keep-awake are handled by DevPilot.
