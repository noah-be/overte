// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { once } from 'node:events';
import { NativeHeartbeat } from './socket-heartbeat.mjs';
import { WebSocketServer, WebSocket } from 'ws';

test('a rejected duplicate native connection cannot own the original session lifecycle', async () => {
    const source = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
    const handler = source.slice(source.indexOf("nativeServer.on('connection', native => {"), source.indexOf('const heartbeat = setInterval'));
    const nativeServer = new WebSocketServer({ host: '127.0.0.1', port: 0 });
    const sockets = new Set(); const sessions = new Map(); let closes = 0;
    const session = { token: 'owned-session-test-token', muted: true, closed: false,
        waitForDomain() {}, close() { closes++; this.closed = true; }, browser: { readyState: 0 } };
    sessions.set('test-session', session);
    vm.runInNewContext(handler, { nativeServer, sessions, sockets, setTimeout, clearTimeout, NativeHeartbeat,
        send(socket, message) { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message)); },
        equal: (a, b) => a === b });
    await once(nativeServer, 'listening');
    const endpoint = `ws://127.0.0.1:${nativeServer.address().port}`;
    const original = new WebSocket(endpoint); let duplicate;
    try {
        await once(original, 'open');
        const approved = once(original, 'message');
        original.send(JSON.stringify({ type: 'nativeHello', token: session.token }));
        assert.equal(JSON.parse((await approved)[0]).type, 'mute');
        const originalNative = session.native;
        duplicate = new WebSocket(endpoint); await once(duplicate, 'open');
        duplicate.send(JSON.stringify({ type: 'nativeHello', token: session.token }));
        await once(duplicate, 'close');
        assert.equal(closes, 0, 'The rejected socket never acquires session teardown ownership');
        assert.equal(session.native, originalNative);
        assert.equal(original.readyState, WebSocket.OPEN);
        const previous = session.lastNativeMessage;
        await new Promise(resolve => setTimeout(resolve, 5));
        original.send(JSON.stringify({ type: 'heartbeat' }));
        const deadline = Date.now() + 1000;
        while (session.lastNativeMessage === previous && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 5));
        assert.ok(session.lastNativeMessage > previous, 'The original authenticated socket continues processing real frames');
        original.close(); await once(original, 'close');
        assert.equal(closes, 1, 'Only the owning socket performs session teardown');
    } finally {
        original.terminate(); duplicate?.terminate();
        for (const socket of nativeServer.clients) socket.terminate();
        await new Promise(resolve => nativeServer.close(resolve));
    }
});
