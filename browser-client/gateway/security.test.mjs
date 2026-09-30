// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { domainAddress, pose, validateNativePermissions, EXPOSED_PERMISSION_KEYS, nativeDomainAddress, ASSET_SANDBOX_POLICY, approvedAssetAddress } from './validation.mjs';

test('asset destinations use only the configured authority and preserve resource paths', () => {
    const origins = new Set(['https://assets.example:8443', 'http://127.0.0.1:45110']);
    const requested = new URL('https://assets.example:8443/models/../textures/checker.png?version=2#ignored');
    const destination = approvedAssetAddress(requested, origins);
    assert.notEqual(destination, requested);
    assert.equal(destination.href, 'https://assets.example:8443/textures/checker.png?version=2');
    // Even authority-looking paths stay paths on the configured server.
    assert.equal(approvedAssetAddress('https://assets.example:8443//attacker.example/texture?next=https://attacker.example', origins).host, 'assets.example:8443');
    assert.equal(approvedAssetAddress('https://assets.example:8443/%2f%2fattacker.example/texture', origins).host, 'assets.example:8443');
    assert.equal(approvedAssetAddress('https://assets.example:8443\\@attacker.example/texture', origins).host, 'assets.example:8443');
    assert.equal(approvedAssetAddress('http://127.0.0.1:45110/model.gltf', origins).href, 'http://127.0.0.1:45110/model.gltf');
});
test('asset authorities cannot escape via credentials, redirects, host suffixes or protocols', () => {
    const origins = new Set(['https://assets.example:8443']);
    for (const address of [
        'https://assets.example:8443.attacker.example/texture', 'https://assets.example:8443@attacker.example/texture',
        'https://attacker.example@assets.example:8443/texture', 'https://attacker.example\\@assets.example:8443/texture',
        'https://assets.example/texture', 'http://assets.example:8443/texture', 'file:///etc/passwd',
        'https://assets.example.attacker.example:8443/texture', 'https://127.0.0.1:8443/admin',
    ]) assert.throws(() => approvedAssetAddress(address, origins));
    const permitted = approvedAssetAddress('https://assets.example:8443/model.gltf', origins);
    assert.throws(() => approvedAssetAddress(new URL('//attacker.example/redirected', permitted), origins));
    assert.equal(approvedAssetAddress(new URL('../textures/local.png', permitted), origins).href, 'https://assets.example:8443/textures/local.png');
    assert.throws(() => approvedAssetAddress('https://assets.example:8443/model', new Set(['https://assets.example:8443/path'])));
});

test('invalid session limits cannot silently disable the native process bound', async () => {
    for (const value of ['NaN', 'Infinity', '0', '-1', '1.5']) {
        const child = spawn(process.execPath, ['gateway/server.mjs'], {
            cwd: new URL('..', import.meta.url), env: { ...process.env, OVERTE_GATEWAY_MAX_SESSIONS: value },
            stdio: ['ignore', 'ignore', 'pipe'],
        });
        let errors = ''; child.stderr.on('data', data => { errors += data; });
        const [code] = await once(child, 'exit');
        assert.notEqual(code, 0); assert.match(errors, /must be a positive safe integer/);
    }
});
test('asset navigation is sandboxed and cannot run script in the gateway origin', () => {
    assert.match(ASSET_SANDBOX_POLICY, /(?:^|;)\s*sandbox(?:;|$)/);
    assert.doesNotMatch(ASSET_SANDBOX_POLICY, /allow-scripts|allow-same-origin|allow-forms/);
    assert.match(ASSET_SANDBOX_POLICY, /script-src 'none'/);
});
test('domain addresses canonicalize aliases and reject non-domain/auth inputs', () => {
    assert.equal(domainAddress('localhost:45102'), 'overte://localhost:45102');
    assert.equal(domainAddress('hifi://localhost:45102'), 'overte://localhost:45102');
    for (const input of ['https://example.org', 'overte://user:secret@example.org', 'file:///etc/passwd', 'overte://localhost#hidden', null, '']) assert.throws(() => domainAddress(input));
});
test('native destination is pinned and cannot inherit localhost shared-memory routing', async () => {
    const resolver = async host => [{ address: host === 'local.example' ? '127.0.0.1' : host === 'managed.example' ? '192.0.2.1' : host, family: 4 }];
    await assert.rejects(nativeDomainAddress('overte://127.0.0.1:45102', resolver), /shared memory/);
    await assert.rejects(nativeDomainAddress('overte://local.example:45102', resolver), /shared memory/);
    assert.equal(await nativeDomainAddress('overte://127.0.0.2:45102', resolver), 'overte://127.0.0.2:45102');
    assert.equal(await nativeDomainAddress('overte://managed.example:45102/path', resolver), 'overte://192.0.2.1:45102/path');
});
test('poses validate finite values, world bounds and normalized quaternion', () => {
    const valid = { position: { x: 1, y: 2, z: 3 }, orientation: { x: 0, y: 0, z: 0, w: 1 } };
    assert.equal(pose(valid).type, 'pose');
    assert.throws(() => pose({ ...valid, position: { ...valid.position, x: Infinity } }));
    assert.throws(() => pose({ ...valid, orientation: { x: 0, y: 0, z: 0, w: 0 } }));
    assert.throws(() => pose({ ...valid, velocity: { x: 1000, y: 0, z: 0 } }));
});
test('native permission reports fail closed on elevated, missing or different-domain privileges', () => {
    const expected = Object.fromEntries(EXPOSED_PERMISSION_KEYS.map(key => [key, key === 'id_can_connect' || key === 'id_can_view_asset_urls']));
    assert.doesNotThrow(() => validateNativePermissions(expected, expected, 'hifi://test:40102/0,1,0', 'overte://test:40102'));
    assert.throws(() => validateNativePermissions({ ...expected, id_can_kick: true }, expected, 'overte://test:40102', 'overte://test:40102'));
    assert.throws(() => validateNativePermissions({}, expected, 'overte://test:40102', 'overte://test:40102'));
    assert.throws(() => validateNativePermissions(expected, expected, 'overte://other:40102', 'overte://test:40102'));
});

let gateway, endpoint, origin;
before(async () => {
    const socket = createServer().listen(0, '127.0.0.1'); await once(socket, 'listening');
    const port = socket.address().port; await new Promise(resolve => socket.close(resolve));
    endpoint = `http://127.0.0.1:${port}`; origin = endpoint;
    gateway = spawn(process.execPath, ['gateway/server.mjs'], { cwd: new URL('..', import.meta.url), env: {
        ...process.env, OVERTE_INTERFACE: '', OVERTE_GATEWAY_PORT: String(port), OVERTE_GATEWAY_HOST: '127.0.0.1',
        OVERTE_GATEWAY_DOMAINS: 'overte://127.0.0.1:45102', OVERTE_GATEWAY_ORIGINS: origin,
    }, stdio: ['ignore', 'pipe', 'pipe'] });
    await once(gateway.stdout, 'data');
});
after(async () => { gateway.kill('SIGTERM'); await once(gateway, 'exit'); });
async function authentication() {
    const response = await fetch(`${endpoint}/api/session`);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('set-cookie'), /HttpOnly; SameSite=Strict/);
    return response.headers.get('set-cookie').split(';')[0];
}
async function browser(cookie, requestOrigin = origin) {
    const ws = new WebSocket(endpoint.replace('http:', 'ws:') + '/session', { headers: { Cookie: cookie, Origin: requestOrigin } });
    await once(ws, 'open'); return ws;
}
async function message(ws, input) {
    const received = once(ws, 'message'); ws.send(JSON.stringify(input));
    return JSON.parse((await received)[0]);
}
test('configuration exposes explicitly enabled domains and native gateway mode', async () => {
    const result = await (await fetch(`${endpoint}/api/config`)).json();
    assert.equal(result.transport, 'native-gateway'); assert.equal(result.domains.length, 1);
    assert.equal(result.audio.outputChannels, 2);
});
test('WebSocket rejects untrusted Origin and missing session cookie', async () => {
    for (const options of [{ Origin: 'https://untrusted.example' }, { Origin: origin }]) {
        const ws = new WebSocket(endpoint.replace('http:', 'ws:') + '/session', { headers: options });
        const [error] = await once(ws, 'error'); assert.match(error.message, /403/);
    }
});
test('assets cannot be read without an owned active session', async () => {
    const response = await fetch(`${endpoint}/api/assets/other-session?url=atp:/private.glb`, { headers: { Cookie: await authentication() } });
    assert.equal(response.status, 403);
});
test('gateway denies unauthorized domains and recovers after a failed launch', async () => {
    const ws = await browser(await authentication());
    const rejected = await message(ws, { type: 'join', domain: 'overte://not-enabled.example' });
    assert.equal(rejected.state, 'error'); assert.match(rejected.message, /not enabled/);
    // Failure emits teardown state; wait for it before the next join.
    await new Promise(resolve => setTimeout(resolve, 20));
    const missing = await message(ws, { type: 'join', domain: 'overte://127.0.0.1:45102' });
    assert.equal(missing.state, 'error'); assert.match(missing.message, /OVERTE_INTERFACE/);
    ws.close(); await once(ws, 'close');
});
test('native bridge requires a per-session secret', async () => {
    const ws = new WebSocket(endpoint.replace('http:', 'ws:') + '/native'); await once(ws, 'open');
    ws.send(JSON.stringify({ type: 'nativeHello', token: 'not-a-session-secret' })); await once(ws, 'close');
});
