// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('./native-world.js', import.meta.url), 'utf8');
function fixture() {
    let clock = 0, owner = 'domain:1', nextTimer = 0;
    const timers = new Map(), sent = [], errors = [], reads = [];
    const entities = Array.from({ length: 30 }, (_, index) => ({ id: String(index), type: 'Box', age: 1, color: { red: index } }));
    const context = vm.createContext({ Date, Object, Array, Math, JSON, Error });
    vm.runInContext(source, context);
    const stream = context.createBrowserWorldStream({ budgetMs: 8, now: () => clock, authority: () => owner,
        readIDs: () => entities.map(entity => entity.id),
        readEntity: id => { clock += 3; reads.push(id); return entities.find(entity => entity.id === id); },
        send: message => sent.push(JSON.parse(JSON.stringify(message))), onError: message => errors.push(message),
        schedule: (callback, delay) => { assert.equal(delay, 16); timers.set(++nextTimer, callback); return nextTimer; },
        cancel: timer => timers.delete(timer),
    });
    function tick() { const [id, callback] = timers.entries().next().value; timers.delete(id); callback(); }
    function finish() { for (let count = 0; timers.size; count++) { assert(count < 1000); tick(); } }
    return { stream, entities, timers, sent, errors, reads, tick, finish, setOwner(value) { owner = value; } };
}

test('large native worlds yield between bounded acquisition slices and emit an ordered real snapshot', () => {
    const f = fixture(); f.stream.poll();
    assert.equal(f.reads.length, 3, 'One slow property read may finish after the budget; another cannot start');
    assert.equal(f.timers.size, 1); assert.equal(f.sent.length, 0);
    f.stream.poll(); assert.equal(f.reads.length, 3, 'Concurrent poll cannot start another acquisition');
    f.finish();
    assert.deepEqual(f.sent, [{ type: 'entities', entities: f.entities }]);
    assert.deepEqual(f.reads, f.entities.map(entity => entity.id));
    assert.deepEqual(f.errors, []);
});
test('completed scans preserve stable deduplication, changed data, additions and deletions', () => {
    const f = fixture(); f.stream.poll(); f.finish(); f.sent.length = 0;
    for (const entity of f.entities) { entity.age++; entity.ageAsText = 'new age'; entity.renderInfo = { drawCalls: 5 }; }
    f.stream.poll(); f.finish(); assert.deepEqual(f.sent, []);
    f.entities[4].color.red = 201; f.entities.splice(7, 1); f.entities.push({ id: 'added', type: 'Sphere' });
    f.stream.poll(); f.finish();
    assert.equal(f.sent.length, 1);
    assert.deepEqual(f.sent[0], { type: 'entityUpdates', entities: [f.entities[4], f.entities.at(-1)], removed: ['7'] });
});
test('revocation discards a partial scan and replacement authority gets its own complete snapshot', () => {
    const f = fixture(); f.stream.poll(); const oldCallback = [...f.timers.values()][0];
    f.setOwner(null); f.tick(); assert.deepEqual(f.sent, []); assert.equal(f.timers.size, 0);
    f.setOwner('other-domain:2'); f.entities.splice(0, f.entities.length, { id: 'replacement', type: 'Box' });
    f.stream.poll(); f.finish(); oldCallback();
    assert.deepEqual(f.sent, [{ type: 'entities', entities: f.entities }]);
    assert.equal(f.timers.size, 0);
});
test('stopping cancels pending work and invalid collections fail without publishing partial data', () => {
    const f = fixture(); f.stream.poll(); const callback = [...f.timers.values()][0]; f.stream.stop(); callback(); f.stream.poll();
    assert.deepEqual(f.sent, []); assert.equal(f.timers.size, 0);
    const g = fixture(); g.entities.length = 100001; g.stream.poll();
    assert.deepEqual(g.sent, []); assert.equal(g.errors.length, 1); assert.equal(g.timers.size, 0);
});
test('a dispatched old callback cannot detach the replacement authority timer', () => {
    const f = fixture(); f.stream.poll(); const oldCallback = [...f.timers.values()][0];
    f.setOwner('replacement:2'); f.stream.poll(); assert.equal(f.timers.size, 1);
    oldCallback(); assert.equal(f.timers.size, 1);
    f.stream.stop(); assert.equal(f.timers.size, 0); assert.deepEqual(f.sent, []);
});
