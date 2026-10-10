"""Native author, color, freshness and revision are mandatory replication evidence."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.android.collaboration_observation import actor_receipt, portable_observation


class CollaborationObservationTests(unittest.TestCase):
    def setUp(self):
        self.native = {"schemaVersion": 1, "actorId": "OVERTE_E2E_ACTOR_FIXTURE",
                       "entityName": "OVERTE_E2E_SHARED_COLOR", "revision": 1, "value": "orange",
                       "actorSessionId": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"}
        self.actor = {**self.native, "commandId": "a" * 32}
        self.probe = {"sampleSequence": 20, "sampleEpochMs": 99000}
        self.envelope = {"schemaVersion": 1, "sampleSequence": 21, "sampleEpochMs": 99500,
                         "entityCount": 1, "observation": dict(self.native)}

    def test_native_author_is_verified_then_removed_from_public_evidence(self):
        result = portable_observation(self.envelope, self.actor, 100000, self.probe)
        self.assertEqual(result, {k: v for k, v in self.native.items() if k != "actorSessionId"})
        self.assertNotIn(self.native["actorSessionId"], json.dumps(result))
        for field, value in (("actorSessionId", "bbbbbbbb-1111-2222-3333-aaaaaaaaaaaa"),
                             ("revision", 0), ("value", "blue"), ("actorId", "OVERTE_E2E_ACTOR_OTHER")):
            envelope = copy.deepcopy(self.envelope)
            envelope["observation"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                portable_observation(envelope, self.actor, 100000, self.probe)

    def test_stale_ambiguous_or_malformed_measurements_cannot_pass(self):
        mutations = ({"sampleEpochMs": 90000}, {"sampleEpochMs": 100001}, {"sampleEpochMs": float('nan')},
                     {"sampleSequence": 18}, {"sampleSequence": True}, {"entityCount": 2},
                     {"entityCount": True}, {"schemaVersion": True}, {"observation": None},
                     {"unexpected": True})
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                portable_observation({**self.envelope, **mutation}, self.actor, 100000, self.probe)
        for field, invalid in (("actorSessionId", "00000000-0000-0000-0000-000000000000"),
                               ("revision", True), ("revision", -1), ("revision", 2**53),
                               ("value", []), ("schemaVersion", True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                actor_receipt({**self.actor, field: invalid})

    def test_actor_command_and_initial_revision_must_agree(self):
        for changes in ({"commandId": "seed"}, {"revision": 0}, {"commandId": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                actor_receipt({**self.actor, **changes})
        self.assertEqual(actor_receipt({**self.actor, "commandId": "seed", "revision": 0})["revision"], 0)

    def test_production_probe_requires_real_color_and_nonzero_native_author(self):
        source = (ROOT / "probe/overte_e2e_probe.js").read_text()
        function = source[source.index("    function controlledSharedObservation("):
                          source.index("    function controlledPeer(")]
        script = r'''
const assert = require('assert');
FUNCTION
const author = 'aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb';
const state = {contract:'overte-e2e-collaboration-v1',actorId:'OVERTE_E2E_ACTOR_FIXTURE',revision:1,value:'orange'};
const input = {name:'OVERTE_E2E_SHARED_COLOR',userData:JSON.stringify(state),lastEditedBy:'{'+author+'}',
    color:{red:255,green:150,blue:40}};
assert.equal(controlledSharedObservation(input).actorSessionId,author);
for (const changes of [{color:{red:40,green:120,blue:255}}, {lastEditedBy:null},
    {lastEditedBy:'00000000-0000-0000-0000-000000000000'}, {name:'another-entity'}, {userData:'invalid'}]) {
    assert.equal(controlledSharedObservation({...input,...changes}),null);
}
for (const changes of [{revision:true},{revision:'1'},{revision:-1},{revision:2**53},
    {actorId:'OVERTE_E2E_ACTOR_OTHER'},{value:'green'},{contract:'another-contract'}]) {
    assert.equal(controlledSharedObservation({...input,userData:JSON.stringify({...state,...changes})}),null);
}
'''.replace('FUNCTION', function)
        subprocess.run(['node', '-e', script], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
