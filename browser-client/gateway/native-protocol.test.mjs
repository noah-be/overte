// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { inspectNativeProtocol } from './native-protocol.mjs';

test('native protocol inspection reads actual executable output and owns its child', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-protocol-test-'));
    try {
        const filename = path.join(directory, 'protocol.txt'), ownedProcesses = [];
        const signature = await inspectNativeProtocol({ executable: process.execPath,
            args: ['-e', "require('fs').writeFileSync(process.argv[1], 'ViLohxhZMTalcuUKwgs63g==')", filename],
            filename, ownedProcesses, signal: new AbortController().signal });
        assert.equal(signature, 'ViLohxhZMTalcuUKwgs63g==');
        assert.equal(ownedProcesses.length, 1); assert.equal(ownedProcesses[0].exitCode, 0);
    } finally { await rm(directory, { recursive: true, force: true }); }
});

for (const reason of ['cancel', 'timeout']) test(`protocol inspection ${reason} awaits a TERM-resistant real child`, async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-protocol-test-'));
    const filename = path.join(directory, 'ready'), ownedProcesses = [], controller = new AbortController();
    try {
        const pending = inspectNativeProtocol({ executable: process.execPath,
            args: ['-e', "process.on('SIGTERM',()=>{});require('fs').writeFileSync(process.argv[1],'ready');setInterval(()=>{},1000)", filename],
            filename, ownedProcesses, signal: controller.signal, timeoutMilliseconds: reason === 'timeout' ? 500 : 5000,
            terminationGrace: 30 });
        const rejected = assert.rejects(pending, reason === 'timeout' ? /timed out/ : /cancelled/);
        for (let tries = 0; tries < 100; tries++) {
            try { await access(filename); break; } catch { await new Promise(resolve => setTimeout(resolve, 10)); }
        }
        await access(filename);
        if (reason === 'cancel') controller.abort();
        await rejected;
        assert.equal(ownedProcesses[0].signalCode, 'SIGKILL');
        assert.throws(() => process.kill(ownedProcesses[0].pid, 0), { code: 'ESRCH' });
    } finally { for (const child of ownedProcesses) if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); await rm(directory, { recursive: true, force: true }); }
});
