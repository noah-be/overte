// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { observeSessionMessages } from './session-message-evidence.mjs';

class ActualAPIShapeWorker extends EventTarget {
    writes = []; terminated = 0;
    postMessage(...values) { this.writes.push(values); }
    terminate() { this.terminated++; return 'terminated'; }
    emit(data) { this.dispatchEvent(new MessageEvent('message', { data })); }
}
function environment() {
    const window = { Worker: ActualAPIShapeWorker };
    runInNewContext(`(${observeSessionMessages.toString()})();`, {
        window, URL, location: { href: 'http://127.0.0.1:46106/' }, performance,
    });
    return window;
}

test('passive worker evidence preserves the first exact sanitized failure before later disconnected notices', () => {
    const scope = environment(), worker = new scope.Worker('/assets/session-worker-real.js', { type: 'module' });
    const delivered = [], payload = { type: 'event', generation: 'PRIVATE-GENERATION', event: { type: 'entities', entities: ['PRIVATE-ENTITY'] } };
    worker.addEventListener('message', event => delivered.push(event.data));
    worker.emit(payload); worker.postMessage(payload);
    worker.emit({ type: 'fatal', generation: 'PRIVATE-GENERATION', terminal: false,
        message: 'The renderer stopped accepting bounded session updates. Reconnect to continue.' });
    for (let index = 0; index < 80; index++) worker.emit({ type: 'event', event: { type: 'status', state: 'disconnected', message: 'Disconnected' } });
    assert.equal(delivered[0], payload); assert.equal(worker.writes[0][0], payload);
    const result = scope.overteSessionMessageEvidence(), record = result.workers[0];
    assert.equal(record.firstFailure.kind, 'fatal'); assert.equal(record.firstFailure.terminal, false);
    assert.equal(record.firstFailure.reason, 'The renderer stopped accepting bounded session updates. Reconnect to continue.');
    assert.equal(record.events.length, 64); assert.equal(record.evictedEvents, 17);
    assert.ok(!JSON.stringify(result).includes('PRIVATE'));
    assert.equal(worker.terminate(), 'terminated'); assert.equal(worker.terminated, 1);
    assert.equal(scope.overteSessionMessageEvidence().workers[0].terminated, true);
});

test('session message observation omits payloads, endpoints and identifiers and keeps explicit bounds', () => {
    const scope = environment(); new scope.Worker('/assets/model-fbx-worker.js');
    assert.equal(scope.overteSessionMessageEvidence().workers.length, 0);
    const worker = new scope.Worker('/assets/session-worker-test.js?PRIVATE-QUERY');
    worker.emit({ type: 'event', event: { type: 'status', state: 'error',
        message: 'Cannot fetch wss://private.example/session?q=PRIVATE from 12345678-1234-1234-1234-123456789abc' } });
    let result = scope.overteSessionMessageEvidence();
    assert.equal(result.workers[0].firstFailure.reason, 'Cannot fetch [endpoint] from [identifier]');
    assert.ok(!JSON.stringify(result).includes('private.example'));
    worker.emit({ type: 'fatal', message: 'secret PRIVATE' });
    assert.equal(scope.overteSessionMessageEvidence().workers[0].events.at(-1).reason, '[Sensitive protocol reason omitted]');
    for (let index = 0; index < 8; index++) new scope.Worker(`/assets/session-worker-${index}.js`);
    result = scope.overteSessionMessageEvidence();
    assert.equal(result.workers.length, 8); assert.equal(result.observerLimits.evictedWorkers, 1);
});
