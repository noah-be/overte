// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Shared private file-relay client for full direct tests and the quiet motion
// diagnostic. Actual host PID qualification remains in NativeHostActions.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile, rename } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

export async function readNativeHostProof(directory) {
    const proof = JSON.parse(await readFile(resolve(directory, 'host-proof.json'), 'utf8'));
    assert.equal(proof.live, true, proof.error || 'Host must independently qualify the current native process');
    assert.equal(proof.closed, false); assert.equal(proof.browserPrivatePIDNamespacePreserved, true);
    assert.equal(proof.nativeMotionControlVersion, 2, 'Bind the host proof to the reviewed observer version');
    const age = Date.now() / 1000 - proof.hostObservedUnixTime;
    assert.ok(age >= 0 && age <= 3, 'Live host PID/start-tick verification must be fresh');
    return proof;
}

export async function nativeMotionOperation(operation, binding, directory) {
    assert.ok(['motion-move', 'motion-restore'].includes(operation), 'Only fixed native move and restore are allowed');
    const requestId = randomUUID(), path = resolve(directory, 'requests', requestId + '.json');
    const proof = await readNativeHostProof(directory);
    assert.deepEqual(proof.processIdentity, binding.processIdentity);
    assert.equal(proof.nativeSession, binding.nativeSession);
    const request = { requestId, operation, nativeSession: binding.nativeSession,
        processIdentity: proof.processIdentity, issuedUnixTime: Date.now() / 1000, runNonce: proof.runNonce };
    await writeFile(path + '.pending', JSON.stringify(request) + '\n', { mode: 0o600 });
    await rename(path + '.pending', path);
    const resultPath = resolve(directory, 'results', requestId + '.json'), started = Date.now();
    while (Date.now() - started < 16000) {
        if (existsSync(resultPath)) {
            const response = JSON.parse(await readFile(resultPath, 'utf8'));
            assert.equal(response.requestId, requestId); assert.deepEqual(response.processIdentity, binding.processIdentity);
            assert.equal(response.runNonce, request.runNonce);
            assert.equal(response.ok, true, response.error || 'Host native setup operation failed');
            assert.equal(response.operation, operation); assert.equal(response.result.browserMoved, false);
            assert.equal(response.result.session, binding.nativeSession);
            return response.result;
        }
        await new Promise(done => setTimeout(done, 100));
    }
    throw Error('The bounded host native setup operation did not finish');
}
