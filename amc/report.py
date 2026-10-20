"""The daily message: "Distribuirea mailurilor pentru ziua dd.mm.yyyy".

Built from the confirmed plan, in the team's language (ro / en), as plain
text (copy / e-mail) and as an Adaptive Card (Teams Workflows webhook).
"""
from __future__ import annotations

import html
import re
from datetime import date

from .model import ABSENT, EXCLUDED, ROTATION, full_name

T = {
    "ro": {
        "title": "Distribuirea mailurilor pentru ziua {d}",
        "active": "Agenți activi: {names}.",
        "none_active": "Niciun agent activ în rotație.",
        "order": "Ordinea de alocare automată:",
        "interval": "{start}–{end}: {chain}, apoi se reia.",
        "excluded": "Excluși din rotație:",
        "excluded_item": "{name} – {reason}",
        "still_gets": " (primește totuși: {what})",
        "absent": "Absenți:",
        "absent_item": "{name}",
        "backup": " – backup: {names}",
        "rules": "Reguli de alocare, în ordine:",
        "r_thread": "Reply-urile și mailurile din același fir rămân la agentul care a preluat firul.",
        "r_names": "Mailurile în care apar numele, prenumele {team}unui agent merg la acel agent.",
        "r_names_team": "și echipa ",
        "r_to_cc": "Mailurile care au în To/CC adresa unui agent merg la acel agent.",
        "r_keywords": "Reguli cu cuvinte-cheie:",
        "r_rotation": "Restul mailurilor se împart prin rotație, în ordinea de mai sus.",
        "r_backup": "Dacă agentul ales lipsește, mailul merge la backup-ul lui; dacă nici backup-ul nu e disponibil, {then}.",
        "then_rotation": "intră în rotație",
        "then_fallback": "primește categoria „{cat}”",
        "info": "Categorii informative (se adaugă, nu opresc alocarea):",
        "to_rotation": "rotație",
        "to_nobody": "doar categorie/folder",
        "confirmed": "Confirmat de {by} la {at}.",
        "regenerated": "Actualizat de {by} la {at}.",
        "exc": {"own_thread": "firele lui", "named": "mailurile în care e numit", "to_cc": "mailurile în care e în To/CC",
                "rules": "mailurile din reguli", "high_importance": "mailurile cu importanță High"},
        "reason_none": "fără motiv",
    },
    "en": {
        "title": "Mail distribution for {d}",
        "active": "Active agents: {names}.",
        "none_active": "No agent in rotation.",
        "order": "Automatic assignment order:",
        "interval": "{start}–{end}: {chain}, then again from the top.",
        "excluded": "Out of rotation:",
        "excluded_item": "{name} – {reason}",
        "still_gets": " (still gets: {what})",
        "absent": "Absent:",
        "absent_item": "{name}",
        "backup": " – backup: {names}",
        "rules": "Assignment rules, in order:",
        "r_thread": "Replies and mails of the same conversation stay with the agent who owns it.",
        "r_names": "Mails naming the first name, last name {team}of an agent go to that agent.",
        "r_names_team": "and team ",
        "r_to_cc": "Mails with an agent's address in To/CC go to that agent.",
        "r_keywords": "Keyword rules:",
        "r_rotation": "All other mails are shared by rotation, in the order above.",
        "r_backup": "If the chosen agent is absent, the mail goes to his backup; if no backup is available, {then}.",
        "then_rotation": "it goes to rotation",
        "then_fallback": "it gets the category \"{cat}\"",
        "info": "Information categories (added, assignment continues):",
        "to_rotation": "rotation",
        "to_nobody": "category/folder only",
        "confirmed": "Confirmed by {by} at {at}.",
        "regenerated": "Updated by {by} at {at}.",
        "exc": {"own_thread": "own conversations", "named": "mails naming him", "to_cc": "mails with him in To/CC",
                "rules": "rule mails", "high_importance": "high importance mails"},
        "reason_none": "no reason given",
    },
}


def _names(ids, by_id):
    return ", ".join(full_name(by_id[i]) for i in ids if i in by_id)


def build(team: dict, agents: list[dict], rules: list[dict], plan: dict, regenerated: bool = False) -> dict:
    """Returns {"title", "sections": [(heading, [lines])], "text", "html"}."""
    lang = team.get("language", "ro")
    t = T.get(lang, T["ro"])
    by_id = {a["id"]: a for a in agents}
    day = date.fromisoformat(plan["date"])
    title = t["title"].format(d=day.strftime("%d.%m.%Y"))
    states = plan.get("agents", {})
    active = [a["id"] for a in agents if states.get(a["id"], {}).get("state") == ROTATION]
    excluded = [a["id"] for a in agents if states.get(a["id"], {}).get("state") == EXCLUDED]
    absent = [a["id"] for a in agents if a.get("active", True) and states.get(a["id"], {}).get("state", ABSENT) == ABSENT]

    sections = []
    sections.append(("", [t["active"].format(names=_names(active, by_id)) if active else t["none_active"]]))

    order_lines = []
    intervals = plan.get("intervals") or [{"start": "00:00", "end": "23:59", "order": active}]
    for iv in intervals:
        ids = [i for i in iv["order"] if i in by_id and states.get(i, {}).get("state") == ROTATION]
        chain = " → ".join(f"{n}. {full_name(by_id[i])}" for n, i in enumerate(ids, 1)) or "—"
        order_lines.append(t["interval"].format(start=iv["start"], end=iv["end"], chain=chain))
    sections.append((t["order"], order_lines))

    if excluded:
        lines = []
        for i in excluded:
            st = states[i]
            line = t["excluded_item"].format(name=full_name(by_id[i]), reason=st.get("reason") or t["reason_none"])
            if st.get("exceptions"):
                line += t["still_gets"].format(what=", ".join(t["exc"][e] for e in st["exceptions"]))
            lines.append(line)
        sections.append((t["excluded"], lines))

    if absent:
        lines = []
        for i in absent:
            line = t["absent_item"].format(name=full_name(by_id[i]))
            backups = [b for b in by_id[i].get("backups", []) if b in by_id]
            if backups and team["report"].get("include_backups", True):
                line += t["backup"].format(names=_names(backups, by_id))
            lines.append(line)
        sections.append((t["absent"], lines))

    if team["report"].get("include_rules", True):
        lines = []
        if team.get("use_thread", True):
            lines.append(t["r_thread"])
        if team.get("use_names", True):
            lines.append(t["r_names"].format(team=t["r_names_team"] if team.get("name_requires_team", True) else ""))
            if team.get("match_to_cc_address", True):
                lines.append(t["r_to_cc"])
        keyword = [r for r in rules if r.get("enabled", True) and (r["stop"] or r["assign"])]
        if keyword:
            items = []
            for r in keyword:
                if r["assign"].startswith("agent:") and r["assign"][6:] in by_id:
                    target = full_name(by_id[r["assign"][6:]])
                elif r["assign"] == "rotation":
                    target = t["to_rotation"]
                else:
                    target = ", ".join(r["categories"]) or r.get("folder") or t["to_nobody"]
                items.append(f"{r['name']} → {target}")
            lines.append(t["r_keywords"] + " " + "; ".join(items) + ".")
        lines.append(t["r_rotation"])
        then = t["then_rotation"] if team.get("no_backup") == "rotation" else t["then_fallback"].format(cat=team.get("fallback_category"))
        lines.append(t["r_backup"].format(then=then))
        info = [r for r in rules if r.get("enabled", True) and not r["stop"] and not r["assign"]]
        if info:
            lines.append(t["info"] + " " + "; ".join(f"{r['name']} → {', '.join(r['categories'])}" for r in info) + ".")
        sections.append((t["rules"], [f"{n}. {l}" for n, l in enumerate(lines, 1)]))

    who = plan.get("confirmed_by") or ""
    at = (plan.get("_at") or plan.get("confirmed_at") or "")[11:16]
    if who:
        sections.append(("", [(t["regenerated"] if regenerated else t["confirmed"]).format(by=who, at=at)]))

    text_parts = [title, ""]
    for heading, lines in sections:
        if heading:
            text_parts.append(heading)
        text_parts += [(l if (not heading or re.match(r"^\d+\. ", l)) else "• " + l) for l in lines]
        text_parts.append("")
    text = "\n".join(text_parts).strip() + "\n"

    html_parts = [f"<p><b>{html.escape(title)}</b></p>"]
    for heading, lines in sections:
        if heading:
            html_parts.append(f"<p><b>{html.escape(heading)}</b></p><ul>" +
                              "".join(f"<li>{html.escape(l)}</li>" for l in lines) + "</ul>")
        else:
            html_parts += [f"<p>{html.escape(l)}</p>" for l in lines]
    return {"title": title, "sections": sections, "text": text, "html": "".join(html_parts)}


def adaptive_card(report: dict) -> dict:
    """Payload for a Teams Workflows webhook ("Send webhook alerts to a channel / chat")."""
    body = [{"type": "TextBlock", "text": report["title"], "weight": "Bolder", "size": "Medium", "wrap": True}]
    for heading, lines in report["sections"]:
        if heading:
            body.append({"type": "TextBlock", "text": heading, "weight": "Bolder", "wrap": True, "spacing": "Medium"})
            body.append({"type": "TextBlock", "text": "\n".join(f"- {l}" for l in lines), "wrap": True, "spacing": "Small"})
        else:
            body.append({"type": "TextBlock", "text": "\n\n".join(lines), "wrap": True})
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "msteams": {"width": "Full"},
                "body": body,
            },
        }],
    }
