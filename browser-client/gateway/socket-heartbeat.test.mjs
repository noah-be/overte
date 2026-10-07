// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { WebSocket, WebSocketServer } from 'ws';
import { NativeHeartbeat } from './socket-heartbeat.mjs';

test('native liveness requires an exact fresh bidirectional application challenge', async () => {
    const server = new WebSocketServer({ host: '127.0.0.1', port: 0 });
    await once(server, 'listening');
    const accepted = once(server, 'connection');
    const visitor = new WebSocket(`ws://127.0.0.1:${server.address().port}`);
    await once(visitor, 'open'); const [native] = await accepted;
    let now = 1000;
    const heartbeat = new NativeHeartbeat({ send: message => native.send(JSON.stringify(message)), now: () => now });
    native.on('message', data => heartbeat.receive(JSON.parse(data.toString())));
    try {
        const first = once(visitor, 'message'); assert.equal(heartbeat.tick(), true);
        const request = JSON.parse((await first)[0]);
        assert.equal(request.type, 'nativePing'); assert.match(request.nonce, /^[a-f0-9]{32}$/);
        // An active outgoing connection alone proves neither delivery of commands
        // to the native engine nor processing of those commands.
        visitor.send(JSON.stringify({ type: 'heartbeat' }));
        visitor.send(JSON.stringify({ type: 'nativePong', nonce: 'wrong' }));
        await new Promise(resolve => setTimeout(resolve, 10));
        assert.equal(heartbeat.pending.nonce, request.nonce);
        visitor.send(JSON.stringify({ type: 'nativePong', nonce: request.nonce }));
        const deadline = Date.now() + 1000;
        while (heartbeat.pending && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 5));
        assert.equal(heartbeat.pending, null, 'A real native round trip satisfies the challenge');
        now += 30000;
        const next = once(visitor, 'message'); assert.equal(heartbeat.tick(), true);
        const second = JSON.parse((await next)[0]); assert.notEqual(second.nonce, request.nonce);
        assert.equal(heartbeat.receive({ type: 'nativePong', nonce: request.nonce }), false, 'Old responses cannot acknowledge a new challenge');
        now += 29999; assert.equal(heartbeat.tick(), true);
        now++; assert.equal(heartbeat.tick(), false, 'The existing strict 30-second deadline is retained');
        assert.equal(heartbeat.receive({ type: 'nativePong', nonce: second.nonce }), false, 'Even the correct nonce cannot revive an expired challenge');
    } finally {
        visitor.terminate(); native.terminate(); await new Promise(resolve => server.close(resolve));
    }
});
