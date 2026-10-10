"""Execute the assignment against delayed persisted entities after a restart."""
import subprocess
from pathlib import Path
import unittest


class DomainContentReseedingTests(unittest.TestCase):
    def test_actual_duplicate_entities_are_removed_without_touching_foreign_data(self):
        source = Path(__file__).resolve().parents[1] / "fixture/domain_content_agent.js"
        driver = r'''
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const entities = new Map(), intervals = [], deleted = [];
let nextId = 0, queries = 0, subscribed = false;
const context = {
    print() {},
    Agent: { sessionUUID: 'aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb' },
    EntityViewer: {
        setPosition: p => assert.deepEqual(p,{x:0,y:0,z:0}),
        setCenterRadius: r => { assert.equal(r,1000); subscribed=true; },
        queryOctree: () => { assert.ok(subscribed); queries++; }
    },
    Script: { resolvePath: p => p, setTimeout() {}, setInterval: fn => intervals.push(fn) },
    XMLHttpRequest: function() { this.open=()=>{}; this.setRequestHeader=()=>{}; this.send=()=>{}; },
    Entities: {
        serversExist: () => true, canRez: () => true,
        addEntity: p => { const id='new-'+(++nextId); entities.set(id,{...p}); return id; },
        findEntities: () => [...entities.keys()],
        getEntityProperties: id => entities.get(id) || {},
        deleteEntity: id => { deleted.push(id); entities.delete(id); }
    }
};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
assert.equal(entities.size,5);
assert.equal(deleted.length,0);
// Previously persisted entities can arrive after the first seed scan.
for (const [id,p] of [...entities]) entities.set('persisted-'+id,{...p});
const shared=[...entities.values()].find(p=>p.name==='OVERTE_E2E_SHARED_COLOR');
entities.set('foreign-contract',{...shared,userData:JSON.stringify({contract:'foreign',actorId:'OVERTE_E2E_ACTOR_FIXTURE'})});
entities.set('foreign-actor',{...shared,userData:JSON.stringify({contract:'overte-e2e-collaboration-v1',actorId:'OTHER_ACTOR'})});
entities.set('invalid-data',{...shared,userData:'invalid'});
entities.set('unrelated-name',{...shared,name:'OTHER_ENTITY'});
intervals.forEach(fn=>fn());
assert.equal(deleted.length,5);
assert.ok(deleted.every(id=>id.startsWith('persisted-')));
assert.equal(entities.size,9);
assert.equal([...entities].filter(([id])=>id.startsWith('new-')).length,5);
assert.ok(entities.has('foreign-contract') && entities.has('foreign-actor') && entities.has('invalid-data'));
intervals.forEach(fn=>fn());
assert.equal(deleted.length,5);
// Reconcile another delayed persisted copy without deleting selected identities.
entities.set('late-copy',{...shared});
intervals.forEach(fn=>fn());
assert.ok(!entities.has('late-copy'));
assert.equal(deleted.length,6);
assert.ok(queries>=4);
'''
        subprocess.run(['node', '-e', driver, str(source)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
