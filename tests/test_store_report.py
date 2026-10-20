import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from amc import model, report
from amc.store import Conflict, TeamStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TeamStore(Path(self.tmp.name) / "team")
        self.store.initialize("Echipa Test", "Shared")

    def tearDown(self):
        self.tmp.cleanup()

    def test_initialize_and_conflict(self):
        team = self.store.team()
        self.assertEqual(team["name"], "Echipa Test")
        self.store.save_team({**team, "mode": "folder"}, team["_rev"])
        with self.assertRaises(Conflict):
            self.store.save_team({**team, "mode": "both"}, team["_rev"])
        self.assertEqual(self.store.team()["mode"], "folder")

    def test_plan_round_trip_and_previous(self):
        d1, d2 = date(2026, 10, 20), date(2026, 10, 21)
        self.store.save_plan(d1, {"confirmed": True, "agents": {"a": {"state": "rotation"}},
                                  "intervals": [{"start": "09:00", "end": "08:00", "order": ["a"]},
                                                {"start": "08:00", "end": "12:00", "order": ["a", "a"]}]}, None)
        p = self.store.plan(d1)
        self.assertEqual(p["intervals"], [{"start": "08:00", "end": "12:00", "order": ["a"]}])
        prev = self.store.previous_plan(d2)
        self.assertEqual(prev["date"], "2026-10-20")
        copy = model.plan_from_previous(prev, d2)
        self.assertFalse(copy["confirmed"])
        self.assertEqual(copy["date"], "2026-10-21")

    def test_journal_threads(self):
        today = date.today()
        self.store.journal_append(today, {"id": "1", "conv": "c1", "agent": "ana", "status": "ok"})
        self.store.journal_append(today, {"id": "2", "conv": "c1", "agent": "dan", "status": "reassigned"})
        self.store.journal_append(today, {"id": "3", "conv": "c2", "agent": "eva", "status": "error"})
        self.assertEqual(self.store.thread_owners(), {"c1": "dan"})
        self.assertEqual(self.store.processed_ids(), {"1", "2"})

    def test_hand_edited_file_is_tolerated(self):
        (self.store.folder / "rules.json").write_text(json.dumps({"rules": [
            {"name": "x", "all": "a, b", "assign": "agent:ana", "stop": False, "where": ["nope"]}]}), encoding="utf-8")
        rules, _ = self.store.rules()
        self.assertEqual(rules[0]["all"], ["a", "b"])
        self.assertTrue(rules[0]["stop"])
        self.assertEqual(rules[0]["where"], list(model.WHERE))


class ReportTests(unittest.TestCase):
    def test_romanian_message_and_card(self):
        team = model.normalize_team({"name": "Echipa Test"})
        agents = model.normalize_agents([
            {"id": "a", "first_name": "Ana", "last_name": "Pop", "backups": ["b"]},
            {"id": "b", "first_name": "Bogdan", "last_name": "Ion"},
            {"id": "c", "first_name": "Cris", "last_name": "Vlad"}])
        plan = model.normalize_plan({"confirmed": True, "confirmed_by": "tl",
                                     "agents": {"a": {"state": "absent"}, "b": {"state": "rotation"},
                                                "c": {"state": "excluded", "reason": "Training", "exceptions": ["own_thread"]}},
                                     "intervals": [{"start": "08:00", "end": "16:00", "order": ["c", "b", "a"]}]}, date(2026, 10, 21))
        rep = report.build(team, agents, [], plan)
        self.assertTrue(rep["text"].startswith("Distribuirea mailurilor pentru ziua 21.10.2026"))
        self.assertIn("08:00–16:00: 1. Bogdan Ion, apoi se reia.", rep["text"])
        self.assertIn("Cris Vlad – Training (primește totuși: firele lui)", rep["text"])
        self.assertIn("Ana Pop – backup: Bogdan Ion", rep["text"])
        card = report.adaptive_card(rep)
        self.assertEqual(card["attachments"][0]["contentType"], "application/vnd.microsoft.card.adaptive")
        self.assertEqual(card["attachments"][0]["content"]["body"][0]["text"], rep["title"])

    def test_english(self):
        team = model.normalize_team({"language": "en"})
        plan = model.normalize_plan({"agents": {}}, date(2026, 10, 21))
        self.assertTrue(report.build(team, [], [], plan)["text"].startswith("Mail distribution for 21.10.2026"))


if __name__ == "__main__":
    unittest.main()
