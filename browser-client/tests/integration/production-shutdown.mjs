// SPDX-License-Identifier: Apache-2.0
// Exercise an independently installed production tree against the actual laboratory.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile, writeFile, readdir, stat, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import net from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const distribution = path.resolve(process.env.OVERTE_DISTRIBUTION_ROOT || repo);
const port = 8091;
const baseURL = `http://127.0.0.1:${port}`;
const directory = path.join(repo, 'build/browser-lab/evidence');
const sha = data => createHash('sha256').update(data).digest('hex');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { startedAt: new Date().toISOString(), completed: false, productionOnly: true,
    domain: 'overte://127.0.0.2:45102', checks: [], sourceSHA256: {} };
let gateway, browser, owned = [], profiles = [], gatewayExited;

async function processes() {
    const entries = await readdir('/proc');
    const result = [];
    for (const entry of entries) {
        if (!/^\d+$/.test(entry)) continue;
        try {
            const raw = await readFile(`/proc/${entry}/stat`, 'utf8');
            const fields = raw.slice(raw.lastIndexOf(')') + 2).split(' ');
            result.push({ pid: Number(entry), parent: Number(fields[1]), start: fields[19] });
        } catch (error) { if (!['ENOENT', 'ESRCH', 'EACCES'].includes(error.code)) throw error; }
    }
    return result;
}
async function descendants(pid) {
    const all = await processes(), parents = new Set([pid]), result = [];
    let changed = true;
    while (changed) {
        changed = false;
        for (const child of all) if (parents.has(child.parent) && !parents.has(child.pid)) {
            parents.add(child.pid); result.push(child); changed = true;
        }
    }
    return result;
}
async function requireUnusedPort() {
    await new Promise((resolve, reject) => {
        const socket = net.connect(port, '127.0.0.1');
        socket.once('connect', () => { socket.destroy(); reject(Error('Production test port 8091 is occupied; existing services were preserved.')); });
        socket.once('error', error => error.code === 'ECONNREFUSED' ? resolve() : reject(error));
    });
}
async function bounded(promise, milliseconds, message) {
    let timer;
    try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error(message)), milliseconds); })]); }
    finally { clearTimeout(timer); }
}
try {
    await mkdir(directory, { recursive: true });
    await requireUnusedPort();
    for (const file of ['gateway/server.mjs', 'gateway/process-lifecycle.mjs', 'gateway/native-bridge.js', 'dist/index.html'])
        report.sourceSHA256[`browser-client/${file}`] = sha(await readFile(path.join(distribution, 'browser-client', file)));
    for (const file of await readdir(path.join(distribution, 'browser-client/dist/assets')))
        report.sourceSHA256[`browser-client/dist/assets/${file}`] = sha(await readFile(path.join(distribution, 'browser-client/dist/assets', file)));
    // The extracted deployment needs its two production dependencies only.
    const installed = JSON.parse(await readFile(path.join(distribution, 'browser-client/node_modules/.package-lock.json'), 'utf8'));
    report.productionDependencies = Object.keys(installed.packages).filter(name => name && !name.includes('/node_modules/'));
    assert.deepEqual(report.productionDependencies.sort(), ['node_modules/three', 'node_modules/ws']);
    gateway = spawn(process.execPath, ['gateway/server.mjs'], {
        cwd: path.join(distribution, 'browser-client'), detached: true, stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, DISPLAY: ':94', QT_QPA_PLATFORM: 'xcb', QT_SCALE_FACTOR: '1', QT_AUTO_SCREEN_SCALE_FACTOR: '0',
            OVERTE_INTERFACE: path.join(repo, 'build/browser-lab/appimage/squashfs-root/AppRun'),
            OVERTE_GATEWAY_DOMAINS: report.domain, OVERTE_GATEWAY_NATIVE_SCHEME: 'hifi',
            OVERTE_GATEWAY_PULSEAUDIO: path.join(repo, 'browser-client/lab/pulseaudio-local.sh'),
            OVERTE_GATEWAY_GUEST_POLICY: path.join(repo, 'build/browser-lab/config/guest-policy.json'),
            OVERTE_GATEWAY_ASSET_ORIGINS: 'https://raw.githubusercontent.com,http://127.0.0.1:45110',
            OVERTE_GATEWAY_HOST: '127.0.0.1', OVERTE_GATEWAY_PORT: String(port),
            OVERTE_GATEWAY_ORIGINS: baseURL, OVERTE_GATEWAY_MAX_SESSIONS: '1' },
    });
    gateway.stdout.on('data', () => {});
    gateway.stderr.on('data', () => {});
    gatewayExited = once(gateway, 'exit');
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
        try { ready = (await fetch(`${baseURL}/api/config`)).ok; } catch {}
        if (ready) break;
        if (gateway.exitCode !== null || gateway.signalCode !== null) throw Error('Production gateway exited before listening.');
        await delay(100);
    }
    assert(ready, 'Independently installed production gateway serves its actual distribution');
    browser = await chromium.launch({ headless: true, args: ['--use-angle=swiftshader'],
        env: { ...process.env, PULSE_SERVER: `unix:${repo}/build/browser-lab/runtime/browser-pulse.sock` } });
    report.browserVersion = browser.version();
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
        const Original = window.WebSocket;
        window.__productionProof = { sessionId: null, leaving: false };
        window.WebSocket = class extends Original {
            constructor(...args) {
                super(...args); this.addEventListener('message', event => {
                    if (typeof event.data !== 'string') return;
                    try { const message = JSON.parse(event.data); if (message.sessionId) window.__productionProof.sessionId = message.sessionId; } catch {}
                });
            }
            send(data) {
                if (typeof data === 'string') try { if (JSON.parse(data).type === 'leave') window.__productionProof.leaving = true; } catch {}
                super.send(data);
            }
        };
    });
    await page.goto(baseURL);
    await page.locator('#domain').fill(report.domain);
    await page.locator('#name').fill('Production package visitor');
    await page.locator('#join').click();
    await page.waitForFunction(() => window.__overte?.connected && window.__overte.entityCount >= 7 && window.__overte.avatarCount >= 1, null, { timeout: 90000 });
    await page.waitForFunction(() => document.querySelector('#events').textContent.includes('Loaded Browser Lab ATP Textured Model'), null, { timeout: 30000 });
    assert(await page.locator('#world canvas').evaluate(canvas => !!canvas.getContext('webgl2')), 'Actual production renderer has WebGL2');
    const sessionId = await page.evaluate(() => window.__productionProof.sessionId);
    const texture = await page.request.get(`${baseURL}/api/assets/${sessionId}?url=${encodeURIComponent('atp:/browser-lab/checker.png')}`);
    assert.equal(texture.status(), 200);
    assert.equal(texture.headers()['cache-control'], 'private, no-store');
    assert.match(texture.headers()['content-security-policy'], /sandbox/);
    const bytes = await texture.body();
    assert.equal(sha(bytes), sha(await readFile(path.join(repo, 'browser-client/lab/checker.png'))));
    report.binaryTexture = { bytes: bytes.length, sha256: sha(bytes) };
    report.world = await page.evaluate(() => ({ connected: window.__overte.connected, entities: window.__overte.entityCount, participants: window.__overte.avatarCount }));
    report.checks.push('Production-only install, real entities/native participant, WebGL2, real binary ATP fidelity and asset isolation');
    owned = await descendants(gateway.pid);
    assert(owned.length >= 4, 'Actual gateway owns native Interface, PulseAudio, capture and playback children');
    for (const child of owned) {
        try {
            const environment = (await readFile(`/proc/${child.pid}/environ`, 'utf8')).split('\0');
            const runtime = environment.find(value => value.startsWith(`XDG_RUNTIME_DIR=${path.join(tmpdir(), 'overte-browser-')}`))?.slice('XDG_RUNTIME_DIR='.length);
            if (runtime && !profiles.includes(runtime)) profiles.push(runtime);
        } catch (error) { if (!['ENOENT', 'ESRCH'].includes(error.code)) throw error; }
    }
    assert.equal(profiles.length, 1, 'Session has one private runtime profile');
    const leavingAt = Date.now();
    await page.locator('#leave').click();
    await page.waitForFunction(() => window.__productionProof.leaving);
    assert.equal(gateway.exitCode, null);
    const beforeSignal = await processes();
    const pendingOwnedChildren = owned.filter(child => beforeSignal.some(entry => entry.pid === child.pid && entry.start === child.start)).length;
    assert(pendingOwnedChildren > 0, 'Actual native/audio teardown is still pending when shutdown overlaps leave');
    gateway.kill('SIGTERM');
    await delay(100);
    const repeatedSignal = gateway.exitCode === null && gateway.signalCode === null && gateway.kill('SIGTERM');
    const [code, signal] = await bounded(gatewayExited, 12000, 'Production gateway did not drain real children after concurrent leave and shutdown.');
    assert.equal(code, 0); assert.equal(signal, null);
    const remaining = await processes();
    assert.equal(owned.filter(child => remaining.some(entry => entry.pid === child.pid && entry.start === child.start)).length, 0,
        'Concurrent shutdown leaves no owned native/audio child alive');
    for (const profile of profiles) await assert.rejects(stat(profile), { code: 'ENOENT' });
    report.shutdown = { overlappingLeave: true, repeatedSignal, pendingOwnedChildrenAtSignal: pendingOwnedChildren,
        milliseconds: Date.now() - leavingAt,
        ownedChildren: owned.length, survivingOwnedChildren: 0, removedPrivateProfiles: profiles.length, exitCode: code };
    assert.deepEqual(errors, []);
    report.checks.push('Overlapping browser leave/repeated gateway SIGTERM awaits all real children and removes session profile');
    report.completed = true;
} catch (error) {
    report.error = error.message; process.exitCode = 1; console.error(error);
} finally {
    await browser?.close();
    if (gateway && gateway.exitCode === null && gateway.signalCode === null) {
        gateway.kill('SIGTERM');
        try { await bounded(gatewayExited, 12000, 'Cleanup timeout'); }
        catch { try { process.kill(-gateway.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }
    }
    report.finishedAt = new Date().toISOString();
    await writeFile(path.join(directory, 'production-shutdown.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
}
