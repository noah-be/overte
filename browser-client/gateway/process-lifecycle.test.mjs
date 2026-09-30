// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { terminateProcess } from './process-lifecycle.mjs';

test('teardown waits for graceful child exit before releasing its process slot', async () => {
    const child = spawn(process.execPath, ['-e', 'process.stdout.write("ready");setInterval(()=>{},1000)']);
    await once(child.stdout, 'data');
    await terminateProcess(child);
    assert.equal(child.signalCode, 'SIGTERM');
});
test('teardown awaits SIGKILL for a child that ignores SIGTERM', async () => {
    const child = spawn(process.execPath, ['-e', 'process.on("SIGTERM",()=>{});process.stdout.write("ready");setInterval(()=>{},1000)']);
    await once(child.stdout, 'data');
    await terminateProcess(child, 50);
    assert.equal(child.signalCode, 'SIGKILL');
});
