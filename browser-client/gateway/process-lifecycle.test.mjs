// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { terminateProcess, SharedTeardown } from './process-lifecycle.mjs';

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

test('concurrent close callers share cleanup and synchronous permission revocation', async () => {
    const child = spawn(process.execPath, ['-e', 'process.on("SIGTERM",()=>{});process.stdout.write("ready");setInterval(()=>{},1000)']);
    await once(child.stdout, 'data');
    let cleanups = 0, notifications;
    class Session extends SharedTeardown {
        revoke() { this.closed = true; this.permissionsApproved = false; this.muted = true; }
        async teardown(notify) { cleanups++; notifications = notify; await terminateProcess(child, 50); }
    }
    const session = new Session();
    session.permissionsApproved = true; session.muted = false;
    const leaving = session.close(false);
    assert.equal(session.closed, true);
    assert.equal(session.permissionsApproved, false);
    assert.equal(session.muted, true);
    assert.equal(child.signalCode, null, 'Child cleanup is still pending after synchronous revocation');
    const shutdown = session.close(true);
    assert.equal(shutdown, leaving, 'Shutdown must await the exact in-flight cleanup promise');
    await Promise.all([leaving, shutdown]);
    assert.equal(cleanups, 1);
    assert.equal(notifications, false, 'The initiating caller retains its notification choice');
    assert.equal(child.signalCode, 'SIGKILL');
    assert.equal(session.close(), leaving, 'Completed cleanup remains idempotent');
});

test('SIGTERM during leave waits for the already-closing TERM-resistant child', { timeout: 10000 }, async () => {
    const module = new URL('./process-lifecycle.mjs', import.meta.url).href;
    const controller = spawn(process.execPath, ['--input-type=module', '-e', `
        import { spawn } from 'node:child_process';
        import { once } from 'node:events';
        import { SharedTeardown, terminateProcess } from ${JSON.stringify(module)};
        const child = spawn(process.execPath, ['-e', 'process.on("SIGTERM",()=>process.stdout.write("ignored"));process.stdout.write("ready");setInterval(()=>{},1000)']);
        await once(child.stdout, 'data');
        class Session extends SharedTeardown {
            revoke() { this.closed = true; }
            async teardown() { await terminateProcess(child, 500); }
        }
        const session = new Session();
        process.on('SIGTERM', async () => {
            await session.close();
            process.stdout.write('shutdown-clean');
            process.exit(0);
        });
        session.close(false);
        await once(child.stdout, 'data');
        process.stdout.write(JSON.stringify({ pid: child.pid, closed: session.closed }) + '\\n');
    `], { stdio: ['ignore', 'pipe', 'pipe'] });
    let childPid;
    try {
        const [data] = await Promise.race([
            once(controller.stdout, 'data'),
            once(controller, 'exit').then(() => { throw Error('The teardown test controller exited before starting cleanup.'); }),
        ]);
        const started = JSON.parse(data.toString()); childPid = started.pid;
        assert.equal(started.closed, true);
        assert.doesNotThrow(() => process.kill(childPid, 0), 'The owned child is alive while leave cleanup is pending');
        const exited = once(controller, 'exit'); controller.kill('SIGTERM');
        const [code, signal] = await exited;
        assert.equal(code, 0); assert.equal(signal, null);
        assert.throws(() => process.kill(childPid, 0), { code: 'ESRCH' }, 'Shutdown cannot exit while its already-closing child is still alive');
    } finally {
        if (controller.exitCode === null && controller.signalCode === null) await terminateProcess(controller, 50);
        if (childPid) { try { process.kill(childPid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }
    }
});
