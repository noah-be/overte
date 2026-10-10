"""Independent actor commands cannot acknowledge a different or double edit."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.collaboration_broker import ACTOR, ENTITY, CollaborationBroker


class CollaborationBrokerTests(unittest.TestCase):
    def setUp(self):
        self.broker = CollaborationBroker()
        self.seed = {"schemaVersion": 1, "commandId": "seed", "entityName": ENTITY,
                     "actorSessionId": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
                     "value": "blue", "revision": 0, "actorId": ACTOR}
        self.command = {"schemaVersion": 1, "entityName": ENTITY, "value": "orange"}

    def test_exact_acknowledgement_and_duplicate_delivery(self):
        with self.assertRaises(RuntimeError):
            self.broker.submit(self.command)
        self.broker.report(self.seed)
        queued = self.broker.submit(self.command)
        self.assertEqual(queued["revision"], 1)
        self.assertEqual(self.broker.command(), queued)
        with self.assertRaises(RuntimeError):
            self.broker.submit(self.command)
        for field, wrong in (("actorId", "OVERTE_E2E_ACTOR_OTHER"),
                             ("actorSessionId", "bbbbbbbb-1111-2222-3333-aaaaaaaaaaaa"),
                             ("revision", 2), ("value", "blue"), ("commandId", "0" * 32)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.broker.report({**queued, "actorId": ACTOR, field: wrong})
        observed = {**queued, "actorId": ACTOR}
        self.broker.report(observed)
        self.broker.report(observed)
        self.assertEqual(self.broker.command(), {"schemaVersion": 1, "pending": False})
        next_command = self.broker.submit({**self.command, "value": "blue"})
        self.assertEqual(next_command["revision"], 2)
        self.assertNotEqual(next_command["commandId"], queued["commandId"])

    def test_strict_scope_and_types(self):
        self.broker.report(self.seed)
        for invalid in ({**self.command, "entityName": "another-entity"},
                        {**self.command, "schemaVersion": True},
                        {**self.command, "extra": True},
                        {**self.command, "value": []}, {**self.command, "value": "green"}, []):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.broker.submit(invalid)
        for invalid in ({**self.seed, "revision": True}, {**self.seed, "revision": -1},
                        {**self.seed, "value": []}, {**self.seed, "actorId": "other"}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.broker.report(invalid)

    def test_reseed_requires_a_controlled_domain_reset(self):
        self.broker.report(self.seed)
        queued = self.broker.submit(self.command)
        with self.assertRaises(ValueError):
            self.broker.report(self.seed)
        self.broker.report({**queued, "actorId": ACTOR})
        with self.assertRaises(ValueError):
            self.broker.report(self.seed)
        self.broker.reset()
        self.broker.report(self.seed)
        self.assertEqual(self.broker.submit(self.command)["revision"], 1)


if __name__ == '__main__':
    unittest.main()
