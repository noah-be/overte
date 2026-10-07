// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { createVisitorFiles } from './tablet-files.mjs';
import { serveVisitorFiles } from './tablet-files-http.mjs';

async function fixture(action) {
    const directory = await mkdtemp(path.join(tmpdir(), 'visitor-http-'));
    const session = { connected: true, permissionsApproved: true, closed: false, files: await createVisitorFiles(directory) };
    const server = http.createServer((request, response) => {
        void serveVisitorFiles(request, response, new URL(request.url, 'http://localhost'), session, origin => origin === 'https://browser.example');
    });
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    try { await action(`http://127.0.0.1:${server.address().port}/`, session); }
    finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await session.files.close(); await rm(directory, { recursive: true, force: true }); }
}

test('actual HTTP visitor file upload, inventory, inert download and removal preserve bytes', async () => {
    await fixture(async endpoint => {
        const headers = { Origin: 'https://browser.example' };
        const name = 'Visitor image ü.png', target = endpoint + '?name=' + encodeURIComponent(name);
        const bytes = Buffer.from([0, 255, 13, 10, 128]);
        assert.equal((await fetch(target, { method: 'PUT', headers, body: bytes })).status, 200);
        assert.deepEqual(await (await fetch(endpoint)).json(), { files: [{ name, size: bytes.length }] });
        const downloaded = await fetch(target);
        assert.equal(downloaded.status, 200);
        assert.equal(downloaded.headers.get('content-security-policy'), "sandbox; default-src 'none'");
        assert.equal(downloaded.headers.get('x-content-type-options'), 'nosniff');
        assert.match(downloaded.headers.get('content-disposition'), /^attachment;/);
        assert.deepEqual(Buffer.from(await downloaded.arrayBuffer()), bytes);
        assert.equal((await fetch(target, { method: 'DELETE', headers })).status, 200);
        assert.equal((await fetch(target)).status, 404);
    });
});

test('actual HTTP file mutations reject missing or foreign Origin and ended sessions', async () => {
    await fixture(async (endpoint, session) => {
        const target = endpoint + '?name=ordinary.txt';
        for (const origin of [undefined, 'https://attacker.example']) {
            const headers = origin ? { Origin: origin } : {};
            assert.equal((await fetch(target, { method: 'PUT', headers, body: 'denied' })).status, 403);
            assert.equal((await fetch(target, { method: 'DELETE', headers })).status, 403);
        }
        assert.equal((await fetch(endpoint, { headers: { Origin: 'https://attacker.example' } })).status, 403);
        assert.deepEqual(await session.files.list(), []);
        session.closed = true;
        assert.equal((await fetch(endpoint)).status, 403);
    });
});

test('actual HTTP file access rejects paths and approval revoked during asynchronous inventory', async () => {
    await fixture(async (endpoint, session) => {
        assert.equal((await fetch(endpoint + '?name=..%2Fhost-file')).status, 400);
        session.files.list = async () => { session.permissionsApproved = false; return [{ name: 'private.txt', size: 1 }]; };
        const result = await fetch(endpoint);
        assert.equal(result.status, 403);
        assert.equal((await result.text()).includes('private.txt'), false);
    });
});
