import unittest
from datetime import date, datetime

from amc import textmatch as tm
from amc.engine import Context, backup_chain, decide
from amc.model import (normalize_agents, normalize_plan, normalize_rules,
                       normalize_team)


def make(team=None, agents=None, rules=None, plan=None, now=None, rotation=None, thread_owners=None):
    team = normalize_team({"name": "Echipa Alfa", "team_aliases": ["Echipa Alfa", "Team Alfa"], **(team or {})})
    agents = normalize_agents(agents if agents is not None else [
        {"id": "ana", "first_name": "Ana", "last_name": "Pop", "email": "ana.pop@example.com", "backups": ["dan"], "folder": "Agenti/Ana"},
        {"id": "dan", "first_name": "Dan", "last_name": "Ionescu", "backups": ["eva"], "folder": "Agenti/Dan"},
        {"id": "eva", "first_name": "Eva", "last_name": "Mureșan", "category": "Eva M.", "folder": "Agenti/Eva"},
    ])
    plan = normalize_plan(plan if plan is not None else {
        "confirmed": True,
        "agents": {"ana": {"state": "rotation"}, "dan": {"state": "rotation"}, "eva": {"state": "rotation"}},
        "intervals": [{"start": "08:00", "end": "12:00", "order": ["ana", "dan", "eva"]},
                      {"start": "12:00", "end": "17:00", "order": ["eva", "dan"]}],
    }, date(2026, 10, 21))
    return Context(team=team, agents=agents, rules=normalize_rules(rules or []), plan=plan,
                   rotation=rotation or {}, thread_owners=thread_owners or {},
                   now=now or datetime(2026, 10, 21, 9, 30))


def mail(**kw):
    base = {"id": "m1", "subject": "Cerere", "body": "Bună ziua", "sender_name": "Client", "sender_email": "client@firma.test",
            "to": [{"name": "Shared", "email": "shared@example.com"}], "cc": [], "attachments": [], "importance": "normal"}
    base.update(kw)
    return base


class TextMatch(unittest.TestCase):
    def test_diacritics_and_case(self):
        t = tm.normalize("FACTURĂ restanță – Şef ţară")
        self.assertTrue(tm.contains("factura", t))
        self.assertTrue(tm.contains("Restanta", t))
        self.assertTrue(tm.contains("sef tara", t))

    def test_whole_words_and_wildcard(self):
        t = tm.normalize("facturile lunii trecute")
        self.assertFalse(tm.contains("factura", t))
        self.assertTrue(tm.contains("factur*", t))
        self.assertFalse(tm.contains("lun", t))

    def test_email_kept(self):
        t = tm.normalize("Scrieți la ana.pop@example.com, mulțumesc.")
        self.assertTrue(tm.contains("ana.pop@example.com", t))


class Rotation(unittest.TestCase):
    def test_strict_order_and_pointer(self):
        ctx = make()
        d = decide(mail(), ctx)
        self.assertEqual((d.step, d.agent_id, d.categories), ("rotation", "ana", ["Ana Pop"]))
        ctx.rotation[d.rotation_key] = d.rotation_next
        self.assertEqual(decide(mail(), ctx).agent_id, "dan")

    def test_skips_excluded_and_absent(self):
        ctx = make(plan={"confirmed": True, "agents": {"ana": {"state": "excluded", "reason": "training"},
                                                        "dan": {"state": "absent"}, "eva": {"state": "rotation"}},
                         "intervals": [{"start": "08:00", "end": "17:00", "order": ["ana", "dan", "eva"]}]})
        self.assertEqual(decide(mail(), ctx).agent_id, "eva")

    def test_interval_by_time(self):
        ctx = make(now=datetime(2026, 10, 21, 13, 0))
        self.assertEqual(decide(mail(), ctx).agent_id, "eva")

    def test_before_first_interval_uses_first(self):
        ctx = make(now=datetime(2026, 10, 21, 7, 0))
        self.assertEqual(decide(mail(), ctx).agent_id, "ana")

    def test_outside_fallback(self):
        ctx = make(team={"outside_intervals": "fallback"}, now=datetime(2026, 10, 21, 19, 0))
        d = decide(mail(), ctx)
        self.assertEqual((d.step, d.categories), ("fallback", ["De verificat"]))

    def test_wait_until_confirmed(self):
        ctx = make(plan={"confirmed": False, "agents": {"ana": {"state": "rotation"}}})
        self.assertEqual(decide(mail(), ctx).step, "wait")

    def test_unconfirmed_plan_used_when_team_allows(self):
        ctx = make(team={"before_confirmation": "previous_plan"},
                   plan={"confirmed": False, "agents": {"dan": {"state": "rotation"}}})
        self.assertEqual(decide(mail(), ctx).agent_id, "dan")


class Thread(unittest.TestCase):
    def test_owner_from_category(self):
        m = mail(thread=[{"categories": ["Dan Ionescu"], "time": "2026-10-20T10:00"},
                         {"categories": ["Ana Pop"], "time": "2026-10-19T10:00"}])
        d = decide(m, make())
        self.assertEqual((d.step, d.agent_id), ("thread", "dan"))

    def test_owner_from_folder(self):
        m = mail(thread=[{"categories": [], "folder": "\\\\Shared\\Inbox\\Agenti\\Eva", "time": "2026-10-20T10:00"}])
        self.assertEqual(decide(m, make()).agent_id, "eva")

    def test_owner_from_journal(self):
        ctx = make(thread_owners={"conv-1": "eva"})
        self.assertEqual(decide(mail(conversation_id="conv-1"), ctx).agent_id, "eva")

    def test_absent_owner_goes_to_backup_chain(self):
        ctx = make(plan={"confirmed": True, "agents": {"ana": {"state": "absent"}, "dan": {"state": "absent"},
                                                        "eva": {"state": "rotation"}}})
        d = decide(mail(thread=[{"categories": ["Ana Pop"], "time": "1"}]), ctx)
        self.assertEqual((d.agent_id, d.intended_agent_id, d.categories), ("eva", "ana", ["Eva M."]))

    def test_excluded_owner_keeps_own_thread_when_allowed(self):
        ctx = make(plan={"confirmed": True, "agents": {"ana": {"state": "excluded", "exceptions": ["own_thread"]},
                                                        "dan": {"state": "rotation"}}})
        d = decide(mail(thread=[{"categories": ["Ana Pop"], "time": "1"}]), ctx)
        self.assertEqual(d.agent_id, "ana")

    def test_excluded_owner_high_importance(self):
        ctx = make(plan={"confirmed": True, "agents": {"ana": {"state": "excluded", "exceptions": ["high_importance"]},
                                                        "dan": {"state": "rotation"}}})
        m = mail(thread=[{"categories": ["Ana Pop"], "time": "1"}])
        self.assertEqual(decide(m, ctx).agent_id, "dan")
        m["importance"] = "high"
        self.assertEqual(decide(m, ctx).agent_id, "ana")

    def test_no_backup_falls_back(self):
        ctx = make(team={"no_backup": "fallback"},
                   plan={"confirmed": True, "agents": {"ana": {"state": "absent"}, "dan": {"state": "absent"},
                                                        "eva": {"state": "absent"}}})
        d = decide(mail(thread=[{"categories": ["Ana Pop"], "time": "1"}]), ctx)
        self.assertEqual((d.step, d.categories), ("fallback", ["De verificat"]))

    def test_backup_chain_order(self):
        ctx = make()
        self.assertEqual(backup_chain(ctx, "ana"), ["dan", "eva"])
        ctx.team["follow_backups_of_backups"] = False
        self.assertEqual(backup_chain(ctx, "ana"), ["dan"])


class Names(unittest.TestCase):
    def test_full_name_and_team_required(self):
        d = decide(mail(body="Vă rog să preia Dan Ionescu din Echipa Alfa."), make())
        self.assertEqual((d.step, d.agent_id), ("name", "dan"))
        d = decide(mail(body="Vă rog să preia Dan Ionescu."), make())
        self.assertEqual(d.step, "rotation")

    def test_reversed_name_and_diacritics(self):
        d = decide(mail(subject="Pentru Muresan Eva (team alfa)"), make())
        self.assertEqual(d.agent_id, "eva")

    def test_first_name_alone_is_not_enough(self):
        d = decide(mail(body="Salut Dan, Echipa Alfa"), make())
        self.assertEqual(d.step, "rotation")

    def test_address_in_cc(self):
        d = decide(mail(cc=[{"name": "Ana", "email": "Ana.Pop@example.com"}]), make())
        self.assertEqual((d.step, d.agent_id), ("name", "ana"))

    def test_sender_agent_is_ignored(self):
        d = decide(mail(sender_email="ana.pop@example.com", body="Ana Pop, Echipa Alfa"), make())
        self.assertEqual(d.step, "rotation")

    def test_subject_beats_body(self):
        d = decide(mail(subject="Eva Muresan", body="Ana Pop a spus... Echipa Alfa"), make())
        self.assertEqual(d.agent_id, "eva")


class Rules(unittest.TestCase):
    RULES = [
        {"id": "down", "name": "Downtime", "any": ["downtime", "mentenanta"], "categories": ["Info", "Downtime"], "stop": False},
        {"id": "fact", "name": "Facturi restante", "all": ["factur*", "restant*"], "none": ["anulat"],
         "assign": "agent:dan", "categories": ["Facturi"]},
        {"id": "news", "name": "Newsletter", "from": ["newsletter.test"], "folder": "Info/Newsletter"},
        {"id": "urg", "name": "Urgente", "any": ["urgent"], "high_only": True, "assign": "rotation", "categories": ["Urgent"]},
    ]

    def test_info_rule_adds_categories_and_continues(self):
        d = decide(mail(subject="Downtime azi"), make(rules=self.RULES))
        self.assertEqual(d.step, "rotation")
        self.assertEqual(d.categories, ["Info", "Downtime", "Ana Pop"])

    def test_rule_assigns_agent(self):
        d = decide(mail(body="Facturile restante din septembrie"), make(rules=self.RULES))
        self.assertEqual((d.step, d.agent_id, d.categories), ("rule", "dan", ["Facturi", "Dan Ionescu"]))

    def test_none_terms_block(self):
        d = decide(mail(body="Factura restantă a fost anulată... anulat"), make(rules=self.RULES))
        self.assertEqual(d.step, "rotation")

    def test_rule_only_folder(self):
        d = decide(mail(sender_email="info@newsletter.test"), make(rules=self.RULES))
        self.assertEqual((d.step, d.agent_id, d.folder), ("rule_only", "", "Info/Newsletter"))

    def test_high_only(self):
        self.assertEqual(decide(mail(subject="urgent"), make(rules=self.RULES)).rule_id, "")
        d = decide(mail(subject="urgent", importance="high"), make(rules=self.RULES))
        self.assertEqual((d.rule_id, d.step, d.categories), ("urg", "rule", ["Urgent", "Ana Pop"]))

    def test_names_before_rules(self):
        d = decide(mail(body="Factura restanta pentru Eva Muresan, Echipa Alfa"), make(rules=self.RULES))
        self.assertEqual((d.step, d.agent_id), ("name", "eva"))

    def test_rule_without_conditions_never_matches(self):
        d = decide(mail(), make(rules=[{"name": "gol", "assign": "agent:eva"}]))
        self.assertEqual(d.step, "rotation")

    def test_attachment_names_searched(self):
        rules = [{"name": "PDF facturi", "all": ["factura"], "where": ["attachments"], "assign": "agent:eva"}]
        d = decide(mail(attachments=["Factura_123.pdf"]), make(rules=rules))
        self.assertEqual(d.agent_id, "eva")


class Modes(unittest.TestCase):
    def test_folder_mode(self):
        d = decide(mail(), make(team={"mode": "folder"}))
        self.assertEqual((d.categories, d.folder), ([], "Agenti/Ana"))

    def test_both_mode(self):
        d = decide(mail(), make(team={"mode": "both"}))
        self.assertEqual((d.categories, d.folder), (["Ana Pop"], "Agenti/Ana"))

    def test_folder_mode_without_folder_uses_category(self):
        agents = [{"id": "x", "first_name": "Ion", "last_name": "Vlad"}]
        ctx = make(team={"mode": "folder"}, agents=agents,
                   plan={"confirmed": True, "agents": {"x": {"state": "rotation"}}})
        self.assertEqual(decide(mail(), ctx).categories, ["Ion Vlad"])

    def test_no_intervals_whole_day(self):
        ctx = make(plan={"confirmed": True, "agents": {"eva": {"state": "rotation"}, "dan": {"state": "excluded"}}})
        d = decide(mail(), ctx)
        self.assertEqual((d.agent_id, d.rotation_key), ("eva", "00:00-23:59"))


if __name__ == "__main__":
    unittest.main()
