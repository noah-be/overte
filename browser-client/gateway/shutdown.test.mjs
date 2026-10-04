// SPDX-License-Identifier: Apache-2.0
// Real gateway/session processes with isolated executable substitutes. This is a
// lifecycle regression, not an Overte transport/audio integration claim.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { WebSocket } from 'ws';
import { PERMISSION_KEYS } from './permission-policy.mjs';
import { terminateProcess } from './process-lifecycle.mjs';

test('gateway shutdown refuses new work and waits for an already-closing owned session', { timeout: 15000 }, async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-shutdown-test-'));
    const binaries = path.join(directory, 'bin'), processList = path.join(directory, 'children.jsonl');
    const terminationList = path.join(directory, 'termination.jsonl');
    let gateway, browser, pids = [];
    try {
        await mkdir(binaries);
        const executable = `#!${process.execPath}
            if (process.argv[1].endsWith('/pactl')) process.exit(0);
            process.on('SIGTERM', () => require('node:fs').appendFileSync(process.env.OWNED_TEST_TERMINATIONS, process.pid + '\\n'));
            require('node:fs').appendFileSync(process.env.OWNED_TEST_PROCESSES, process.pid + '\\n');
            setInterval(() => {}, 1000);
        `;
        for (const name of ['pactl', 'pulseaudio', 'interface', 'ffmpeg']) {
            await writeFile(path.join(binaries, name), executable, { mode: 0o700 });
        }
        const permissionFlags = Object.fromEntries(PERMISSION_KEYS.map(key => [key, ['id_can_connect', 'id_can_view_asset_urls'].includes(key)]));
        const settingsFile = path.join(directory, 'domain.json');
        await writeFile(settingsFile, JSON.stringify({ version: 2.7, authentication: { enable_oauth2: false },
            security: { standard_permissions: ['localhost', 'anonymous'].map(permissions_id => ({ permissions_id, ...permissionFlags })) } }));
        const policyFile = path.join(directory, 'policy.json');
        const domain = 'overte://127.0.0.2:45102';
        await writeFile(policyFile, JSON.stringify({ version: 1, mode: 'anonymous-baseline', domains: [{ domain, settingsFile }] }));
        const probe = createServer().listen(0, '127.0.0.1'); await once(probe, 'listening');
        const port = probe.address().port; await new Promise(resolve => probe.close(resolve));
        const endpoint = `http://127.0.0.1:${port}`;
        gateway = spawn(process.execPath, ['gateway/server.mjs'], { cwd: new URL('..', import.meta.url), env: {
            ...process.env, PATH: `${binaries}${path.delimiter}${process.env.PATH}`, TMPDIR: directory,
            OWNED_TEST_PROCESSES: processList, OWNED_TEST_TERMINATIONS: terminationList,
            OVERTE_GATEWAY_PORT: String(port), OVERTE_GATEWAY_HOST: '127.0.0.1',
            OVERTE_GATEWAY_DOMAINS: domain, OVERTE_GATEWAY_ORIGINS: endpoint, OVERTE_GATEWAY_GUEST_POLICY: policyFile,
            OVERTE_INTERFACE: path.join(binaries, 'interface'), OVERTE_GATEWAY_PULSEAUDIO: path.join(binaries, 'pulseaudio'),
            // These executable substitutes exercise the gateway's real shared
            // teardown, not native isolation (tested separately with actual bwrap/Xvfb).
            OVERTE_GATEWAY_WORKER_ISOLATION: 'off',
        }, stdio: ['ignore', 'pipe', 'pipe'] });
        await once(gateway.stdout, 'data');
        const authenticated = await fetch(`${endpoint}/api/session`);
        const cookie = authenticated.headers.get('set-cookie').split(';')[0]; await authenticated.json();
        browser = new WebSocket(endpoint.replace('http:', 'ws:') + '/session', { headers: { Cookie: cookie, Origin: endpoint } });
        await once(browser, 'open');
        const connecting = once(browser, 'message'); browser.send(JSON.stringify({ type: 'join', domain }));
        assert.equal(JSON.parse((await connecting)[0]).state, 'connecting');
        const deadline = Date.now() + 3000;
        while (Date.now() < deadline) {
            pids = (await readFile(processList, 'utf8').catch(() => '')).trim().split('\n').filter(Boolean).map(Number);
            if (pids.length === 4) break;
            await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.equal(pids.length, 4, 'A real owned session started its four isolated child processes');
        browser.send(JSON.stringify({ type: 'leave' }));
        let leaveStarted;
        for (let attempt = 0; attempt < 100; attempt++) {
            if ((await readFile(terminationList, 'utf8').catch(() => '')).trim()) { leaveStarted = true; break; }
            await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.equal(leaveStarted, true, 'The browser leave actually began child cleanup before the gateway receives SIGTERM');
        gateway.kill('SIGTERM');
        let refusing;
        for (let attempt = 0; attempt < 30; attempt++) {
            const response = await fetch(`${endpoint}/api/config`); await response.json();
            if (response.status === 503) { refusing = true; break; }
            await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.equal(refusing, true, 'HTTP work is refused immediately while child teardown remains pending');
        const rejectedSocket = new WebSocket(endpoint.replace('http:', 'ws:') + '/session', { headers: { Cookie: cookie, Origin: endpoint } });
        const [error] = await once(rejectedSocket, 'error'); assert.match(error.message, /503/);
        const rejectedJoin = once(browser, 'message'); browser.send(JSON.stringify({ type: 'join', domain }));
        assert.match(JSON.parse((await rejectedJoin)[0]).message, /shutting down/);
        assert.equal((await readFile(processList, 'utf8')).trim().split('\n').length, 4, 'Shutdown cannot start an untracked replacement session');
        gateway.kill('SIGINT');
        const [code, signal] = await once(gateway, 'exit');
        assert.equal(code, 0); assert.equal(signal, null);
        for (const pid of pids) assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' }, 'Every owned child must exit before gateway shutdown');
        assert.equal((await readdir(directory)).some(name => name.startsWith('overte-browser-')), false, 'Private session profiles are deleted before exit');
    } finally {
        browser?.terminate();
        if (gateway) await terminateProcess(gateway, 50);
        for (const pid of pids) { try { process.kill(pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }
        await rm(directory, { recursive: true, force: true });
    }
});
