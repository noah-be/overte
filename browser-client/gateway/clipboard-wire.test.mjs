// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import { WebSocket, WebSocketServer } from 'ws';
import { TabletSession } from './tablet.mjs';

test('actual visitor WebSocket and Tablet handler refuse unsupported controls and preserve allowed clipboard limits', async () => {
    const source = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
    const start = source.indexOf("browserServer.on('connection'");
    const handler = source.slice(start, source.indexOf("nativeServer.on('connection'", start));
    const browserServer = new WebSocketServer({ host: '127.0.0.1', port: 0, maxPayload: 192 * 1024 });
    const sessions = new Map(), commands = [];
    const send = (socket, message) => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message)); };
    // Only native process startup is controlled; the production visitor handler,
    // authentication/capacity guards and Tablet input validation execute unchanged.
    class Session {
        constructor(browser, owner) { this.id = randomUUID(); this.browser = browser; this.owner = owner; }
        async launch() {
            this.connected = true; this.permissionsApproved = true; this.permissionRevision = 1;
            this.tablet = new TabletSession({ sendNative: message => commands.push(message), sendBrowser: message => send(this.browser, message),
                isActive: () => this.connected && !this.closed, getRevision: () => this.permissionRevision });
            send(this.browser, { type: 'state', state: 'connected', sessionId: this.id });
        }
        close() { this.closed = true; this.tablet?.close(); sessions.delete(this.id); }
    }
    vm.runInNewContext(handler, { browserServer, sessions, sockets: new Set(), Session, maximumSessions: 1,
        shuttingDown: false, cookie: request => request.headers.cookie, equal: (a, b) => a === b, send, WebSocket });
    await once(browserServer, 'listening');
    const visitor = new WebSocket(`ws://127.0.0.1:${browserServer.address().port}`, { headers: { Cookie: 'owned-test-cookie' } });
    try {
        await once(visitor, 'open');
        const joined = once(visitor, 'message'); visitor.send(JSON.stringify({ type: 'join', domain: 'overte://fixture' })); await joined;
        const input = { type: 'tablet', action: 'input', event: 'text', sequence: 1, revision: 1 };
        for (const text of ['\0'.repeat(1024), 'x'.repeat(65537)]) {
            const reply = once(visitor, 'message'); visitor.send(JSON.stringify({ ...input, text }));
            const warning = JSON.parse((await reply)[0]); assert.equal(warning.type, 'warning'); assert.match(warning.message, /Invalid tablet text/);
            assert.equal(commands.length, 0, 'Refused raw text never reaches the native clipboard/input surface');
        }
        visitor.send(JSON.stringify({ ...input, text: '\t'.repeat(65536) }));
        const deadline = Date.now() + 1000;
        while (commands.length === 0 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 5));
        assert.equal(commands.length, 1); assert.equal(commands[0].text.length, 65536);
        visitor.send(JSON.stringify({ ...input, sequence: 2, text: 'x'.repeat(192 * 1024) }));
        const [code] = await once(visitor, 'close'); assert.equal(code, 1009);
        assert.equal(commands.length, 1, 'Frames above the existing envelope cannot reach native input');
    } finally {
        visitor.terminate(); for (const socket of browserServer.clients) socket.terminate();
        await new Promise(resolve => browserServer.close(resolve));
    }
});
