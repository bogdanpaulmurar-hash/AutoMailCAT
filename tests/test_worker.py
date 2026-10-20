import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from amc import model
from amc.demo import create_demo_team
from amc.mailbox import DemoMailbox
from amc.store import TeamStore
from amc.worker import TeamWorker


def wait_for(cond, seconds=8):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "team"
        self.store = TeamStore(self.folder)
        create_demo_team(self.store)
        self.workers = []

    def tearDown(self):
        for w in self.workers:
            w.stop()
        self.tmp.cleanup()

    def start(self):
        w = TeamWorker(str(self.folder), demo=True)
        self.workers.append(w)
        w.start()
        return w

    def test_waits_then_distributes_and_follows_thread(self):
        box = DemoMailbox(self.folder)
        w = self.start()
        self.assertTrue(wait_for(lambda: w.role == "leader"))
        first = box.add_mail({"subject": "Întrebare", "body": "Salut"})
        w.request_sweep()
        self.assertTrue(wait_for(lambda: w.waiting == 1))
        self.assertEqual(self.store.journal(date.today()), [])

        agents, _ = self.store.agents()
        plan = model.empty_plan(agents, date.today())
        plan["confirmed"] = True
        self.store.save_plan(date.today(), plan, None)
        w.request_sweep()
        self.assertTrue(wait_for(lambda: len(self.store.journal(date.today())) == 1))
        e = self.store.journal(date.today())[0]
        self.assertEqual((e["status"], e["step"], e["agent"]), ("ok", "rotation", "ana"))

        reply = box.add_mail({"subject": "", "body": "Mulțumesc", "reply_to": first})
        w.mailbox._new.append(reply)  # what the running app does when a demo mail is added
        self.assertTrue(wait_for(lambda: len(self.store.journal(date.today())) == 2))
        e = self.store.journal(date.today())[1]
        self.assertEqual((e["step"], e["agent"]), ("thread", "ana"))

    def test_second_copy_stays_on_standby(self):
        w1 = self.start()
        self.assertTrue(wait_for(lambda: w1.role == "leader"))
        w2 = self.start()
        self.assertTrue(wait_for(lambda: w2.role == "standby"))
        self.assertEqual(w1.role, "leader")


if __name__ == "__main__":
    unittest.main()
