"""Fictional demo team: lets anyone try AutoMailCAT without Outlook (start.bat --demo)."""
from __future__ import annotations

from .store import TeamStore


def create_demo_team(store: TeamStore) -> None:
    store.initialize("Echipa Demo", "Demo shared mailbox", "ro")
    team = store.team()
    team.update({
        "team_aliases": ["Echipa Demo", "Team Demo"],
        "mode": "category",
        "report": {**team["report"], "channel": "copy"},
    })
    store.save_team(team, team["_rev"], "demo")
    agents = [
        {"id": "ana", "first_name": "Ana", "last_name": "Pop", "email": "ana.pop@example.test",
         "folder": "Agenti/Ana Pop", "backups": ["dan", "eva"]},
        {"id": "dan", "first_name": "Dan", "last_name": "Ionescu", "email": "dan.ionescu@example.test",
         "folder": "Agenti/Dan Ionescu", "backups": ["eva"]},
        {"id": "eva", "first_name": "Eva", "last_name": "Mureșan", "email": "eva.muresan@example.test",
         "folder": "Agenti/Eva Muresan", "backups": ["ana"]},
        {"id": "radu", "first_name": "Radu", "last_name": "Stan", "email": "radu.stan@example.test",
         "category": "Radu S.", "backups": ["ana"]},
    ]
    _, rev = store.agents()
    store.save_agents(agents, rev, "demo")
    rules = [
        {"id": "downtime", "name": "Downtime / mentenanță", "any": ["downtime", "mentenanta", "indisponibil"],
         "categories": ["Informare", "Downtime"], "stop": False},
        {"id": "facturi", "name": "Facturi restante", "all": ["factur*", "restant*"], "none": ["anulat*"],
         "assign": "agent:dan", "categories": ["Facturi"]},
        {"id": "newsletter", "name": "Newsletter", "from": ["newsletter.test"], "folder": "Info/Newsletter",
         "categories": ["Newsletter"]},
        {"id": "urgent", "name": "Urgențe", "any": ["urgent"], "high_only": True, "assign": "rotation",
         "categories": ["Urgent"]},
    ]
    _, rev = store.rules()
    store.save_rules(rules, rev, "demo")
