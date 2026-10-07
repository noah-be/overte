// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { nativeMotionOperation, readNativeHostProof } from './native-host-motion.mjs';

const binding = { nativeSession: 'unit-native-session', processIdentity: { pid: 123, startTicks: '456', executable: '/unit/native', cwd: '/unit' } };
async function fixture() {
    const directory = await mkdtemp(resolve(tmpdir(), 'shared-native-relay-'));
    for (const child of ['requests', 'results']) await mkdir(resolve(directory, child));
    const proof = { live: true, closed: false, browserPrivatePIDNamespacePreserved: true, nativeMotionControlVersion: 2,
        hostObservedUnixTime: Date.now() / 1000, runNonce: 'unit-run-nonce', ...binding };
    await writeFile(resolve(directory, 'host-proof.json'), JSON.stringify(proof)); return { directory, proof };
}
async function request(directory) {
    for (let attempts = 0; attempts < 100; attempts++) {
        const files = (await readdir(resolve(directory, 'requests'))).filter(name => name.endsWith('.json'));
        if (files.length) return JSON.parse(await readFile(resolve(directory, 'requests', files[0]), 'utf8'));
        await new Promise(done => setTimeout(done, 5));
    }
    throw Error('The private request was not published');
}

test('shared private relay uses exact current nonce/request/participant and only fixed operations', async () => {
    const { directory, proof } = await fixture();
    try {
        const pending = nativeMotionOperation('motion-move', binding, directory), input = await request(directory);
        assert.equal(input.runNonce, proof.runNonce); assert.equal(input.nativeSession, binding.nativeSession);
        assert.deepEqual(input.processIdentity, binding.processIdentity);
        const result = { browserMoved: false, session: binding.nativeSession };
        await writeFile(resolve(directory, 'results', input.requestId + '.json'), JSON.stringify({ requestId: input.requestId,
            processIdentity: binding.processIdentity, runNonce: input.runNonce, ok: true, operation: 'motion-move', result }));
        assert.deepEqual(await pending, result);
        await assert.rejects(nativeMotionOperation('arbitrary-command', binding, directory), /fixed/);
    } finally { await rm(directory, { recursive: true }); }
});

test('shared relay rejects replayed result nonce and stale/future/closed host qualification', async () => {
    const { directory, proof } = await fixture();
    try {
        const pending = nativeMotionOperation('motion-restore', binding, directory); pending.catch(() => {});
        const input = await request(directory);
        await writeFile(resolve(directory, 'results', input.requestId + '.json'), JSON.stringify({ requestId: input.requestId,
            processIdentity: binding.processIdentity, runNonce: 'old-run-nonce', ok: true, operation: 'motion-restore',
            result: { browserMoved: false, session: binding.nativeSession } }));
        await assert.rejects(pending);
        for (const patch of [{ hostObservedUnixTime: Date.now() / 1000 - 4 }, { hostObservedUnixTime: Date.now() / 1000 + 4 },
            { closed: true }, { live: false }, { nativeMotionControlVersion: 1 }]) {
            await writeFile(resolve(directory, 'host-proof.json'), JSON.stringify({ ...proof, ...patch }));
            await assert.rejects(readNativeHostProof(directory));
        }
    } finally { await rm(directory, { recursive: true }); }
});
