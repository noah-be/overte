// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual read-only public transport proof. This does not claim a browser-render journey.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile, writeFile, mkdir, readdir, access } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { WebSocket } from 'ws';
import { terminateProcess } from '../../gateway/process-lifecycle.mjs';

const root = path.resolve(new URL('../../../', import.meta.url).pathname);
const environmentFile = process.env.OVERTE_PUBLIC_TEST_ENV || path.join(root, 'build/browser-hub-lab/gateway/environment-private.json');
const input = JSON.parse(await readFile(environmentFile, 'utf8'));
const environment = { ...(input.env || input), OVERTE_GATEWAY_PORT: '8093', OVERTE_GATEWAY_HOST: '127.0.0.1',
    OVERTE_GATEWAY_ORIGINS: 'http://127.0.0.1:8093', OVERTE_GATEWAY_MAX_SESSIONS: '1',
    OVERTE_GATEWAY_XVFB: path.join(root, 'build/browser-lab/host-tools/usr/bin/Xvfb'),
    OVERTE_GATEWAY_SLIRP: path.join(root, 'build/browser-native-net/root/usr/bin/slirp4netns') };
const endpoint = 'http://127.0.0.1:8093';
const stabilitySeconds = Number(process.env.OVERTE_PUBLIC_TEST_STABILITY_SECONDS || 0);
if (!Number.isInteger(stabilitySeconds) || stabilitySeconds < 0 || stabilitySeconds > 120) throw Error('Public transport stability proof must be between 0 and 120 seconds.');
const report = { startedAt: new Date().toISOString(), mode: 'actual-public-native-transport', place: 'overte_hub',
    publicMicrophoneEnabled: false, publicWorldMutations: 0, publicAssetUploads: 0 };
const gateway = spawn(process.execPath, [process.env.OVERTE_PUBLIC_TEST_GATEWAY || 'gateway/server.mjs'], { cwd: path.join(root, 'browser-client'), env: environment,
    stdio: ['ignore', 'pipe', 'pipe'] });
let browser, sessionId, profile;
const entities = new Map(), hostTypes = {}, states = [];
let connected = false, frame, tabletSequence = 1;
const temporaryRoot = environment.TMPDIR || tmpdir();
const existing = new Set(await readdir(temporaryRoot));
const failures = [];
const tabletNotices = [], warnings = [];
async function waitFor(condition, timeout = 90000) {
    const deadline = Date.now() + timeout;
    while (!condition()) {
        if (failures.length) throw Error(failures[0]);
        if (Date.now() >= deadline) throw Error('Actual public transport proof timed out.');
        await new Promise(resolve => setTimeout(resolve, 50));
    }
}
try {
    gateway.stderr.on('data', () => {});
    await Promise.race([once(gateway.stdout, 'data'), once(gateway, 'exit').then(() => { throw Error('The isolated proof gateway could not start.'); })]);
    const configuration = await (await fetch(endpoint + '/api/config')).json();
    assert.ok(configuration.domains.some(domain => domain.address === 'overte://overte_hub' && domain.mode === 'public-native-guest'));
    const authenticated = await fetch(endpoint + '/api/session');
    const cookie = authenticated.headers.get('set-cookie').split(';')[0];
    await authenticated.json();
    browser = new WebSocket(endpoint.replace('http:', 'ws:') + '/session', { headers: { Origin: endpoint, Cookie: cookie } });
    browser.on('message', (bytes, binary) => {
        if (binary) return;
        const message = JSON.parse(bytes.toString());
        if (message.type === 'state') {
            states.push(message.state);
            if (message.sessionId) sessionId = message.sessionId;
            connected = message.state === 'connected';
            if (message.state === 'error') failures.push(message.message);
        }
        if (message.type === 'entities') { entities.clear(); for (const entity of message.entities) entities.set(entity.id, entity); }
        if (message.type === 'entityUpdates') {
            for (const id of message.removed) entities.delete(id);
            for (const entity of message.entities) entities.set(entity.id, entity);
            report.incrementalUpdates = (report.incrementalUpdates || 0) + 1;
        }
        if (message.type === 'poseRequest') {
            // This transport-only visitor retains the real native spawn without
            // sending movement or changing the public world.
            report.nativeNavigationRequests = (report.nativeNavigationRequests || 0) + 1;
            browser.send(JSON.stringify({ type: 'poseAccepted', nonce: message.nonce, permissionRevision: message.permissionRevision }));
        }
        if (message.type === 'tablet' && message.kind === 'frame') {
            frame = message;
            browser.send(JSON.stringify({ type: 'tablet', action: 'frameAck', sequence: ++tabletSequence, revision: message.revision, frameSequence: message.sequence, displayed: false }));
        }
        if (message.type === 'tablet' && message.kind !== 'frame') tabletNotices.push({ kind: message.kind,
            screen: message.screen, loading: message.loading, visible: message.visible, message: message.message });
        if (message.type === 'warning') warnings.push(message.message);
    });
    await once(browser, 'open');
    browser.send(JSON.stringify({ type: 'join', domain: 'overte://overte_hub', displayName: 'Browser transport test' }));
    await waitFor(() => connected && entities.size > 100);
    report.actualConnected = true;
    browser.send(JSON.stringify({ type: 'tablet', action: 'open', sequence: 1 }));
    await waitFor(() => frame, 30000);
    assert.ok(frame.data.length > 1000); assert.ok(frame.width > 200 && frame.height > 200);
    report.tabletFrame = { width: frame.width, height: frame.height, bytes: Buffer.from(frame.data, 'base64').length };
    await mkdir(path.join(root, 'build/browser-hub-lab/evidence'), { recursive: true });
    await writeFile(path.join(root, 'build/browser-hub-lab/evidence/public-tablet.png'), Buffer.from(frame.data, 'base64'));
    const model = [...entities.values()].find(entity => typeof entity.modelURL === 'string' && entity.modelURL.startsWith('https:'));
    assert.ok(model);
    const assetURL = new URL(`/api/assets/${sessionId}`, endpoint); assetURL.searchParams.set('url', model.modelURL);
    const asset = await fetch(assetURL, { headers: { Cookie: cookie } });
    assert.equal(asset.status, 200); const bytes = await asset.arrayBuffer(); assert.ok(bytes.byteLength > 0);
    report.actualHTTPSAsset = { origin: new URL(model.modelURL).origin, bytes: bytes.byteLength };
    if (stabilitySeconds) {
        const end = Date.now() + stabilitySeconds * 1000;
        while (Date.now() < end) { if (failures.length) throw Error(failures[0]); await new Promise(resolve => setTimeout(resolve, 100)); }
        assert.ok(connected); report.connectedStabilitySeconds = stabilitySeconds;
    }
    for (const entity of entities.values()) hostTypes[entity.entityHostType || 'unspecified'] = (hostTypes[entity.entityHostType || 'unspecified'] || 0) + 1;
    report.entityCount = entities.size; report.entityHostTypes = hostTypes;
    for (const name of await readdir(temporaryRoot)) {
        if (existing.has(name) || !name.startsWith('overte-browser-')) continue;
        const candidate = path.join(temporaryRoot, name);
        const script = await readFile(path.join(candidate, 'audio.pa'), 'utf8').catch(() => '');
        if (script.includes(sessionId.replaceAll('-', ''))) profile = candidate;
    }
    assert.ok(profile, 'The actual owned session profile is identifiable without reading credentials');
    const privateConfig = JSON.parse(await readFile(path.join(profile, 'native-network.json'), 'utf8'));
    assert.ok(privateConfig.args.includes('--unshare-pid') && privateConfig.args.includes('--unshare-user'));
    report.privateNetworkOwnerConfigured = true;
    browser.send(JSON.stringify({ type: 'leave' }));
    await waitFor(() => states.includes('disconnected'), 20000);
    await assert.rejects(access(profile), { code: 'ENOENT' }); report.privateProfileRemoved = true;
    report.states = states; report.passed = true;
} catch (error) { report.passed = false; report.error = error.message; report.states = states; }
finally {
    if (!report.entityHostTypes) {
        for (const entity of entities.values()) hostTypes[entity.entityHostType || 'unspecified'] = (hostTypes[entity.entityHostType || 'unspecified'] || 0) + 1;
        report.entityCount = entities.size; report.entityHostTypes = hostTypes;
    }
    browser?.close(); await terminateProcess(gateway, 15000);
    report.finishedAt = new Date().toISOString(); report.tabletNotices = tabletNotices; report.warnings = warnings;
    const output = path.join(root, 'build/browser-hub-lab/evidence'); await mkdir(output, { recursive: true });
    await writeFile(path.join(output, 'public-transport.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
}
if (!report.passed) process.exitCode = 1;
