// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted regression coverage for live updates with slow renderer acknowledgments.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SessionEventOutbox, type SessionDelivery } from '../src/protocol/session-events';

const generation = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const authority = { admitted: true, connected: true };

test('live avatar positions reach a busy renderer while entity edits keep arriving', () => {
    const delivered: SessionDelivery[] = [];
    const outbox = new SessionEventOutbox(message => delivered.push(message));
    outbox.enqueue(generation, authority, { type: 'status', state: 'connected' });
    const avatarAcknowledgments: number[] = [];
    for (let acknowledgment = 0; acknowledgment < 8; acknowledgment++) {
        outbox.enqueue(generation, authority, { type: 'upserts', entities: [{ id: 'moving-entity', type: 'Box', alpha: acknowledgment / 10 }] });
        // Network observations continue while the renderer handles its previous edit.
        for (let frame = 0; frame < 30; frame++) outbox.enqueue(generation, authority, {
            type: 'avatars', avatars: [{ id: 'native-peer', position: { x: acknowledgment, y: 0, z: frame } }],
        });
        assert.equal(delivered.length, acknowledgment + 1, 'only one event may be posted before its acknowledgment');
        assert.ok(outbox.queued <= 2, 'repeated live snapshots remain bounded');
        outbox.acknowledge(delivered.at(-1)!.ticket);
        const next = delivered.at(-1)!;
        if (next.event.type === 'avatars') {
            avatarAcknowledgments.push(acknowledgment);
            assert.deepEqual(next.event.avatars[0].position, { x: acknowledgment, y: 0, z: 29 },
                'the received native pose must be the latest observed pose');
        }
    }
    assert.ok(avatarAcknowledgments.length >= 3, 'ongoing entity edits must not indefinitely postpone native pose delivery');
    assert.ok(avatarAcknowledgments[0] < 3, 'the first native update must arrive within a bounded number of renderer acknowledgments');
    for (let index = 1; index < avatarAcknowledgments.length; index++) {
        assert.ok(avatarAcknowledgments[index] - avatarAcknowledgments[index - 1] <= 3,
            'fresh native updates must continue under sustained entity traffic');
    }
});

test('current permission snapshots remain live alongside sustained entity and avatar updates', () => {
    const delivered: SessionDelivery[] = [];
    const outbox = new SessionEventOutbox(message => delivered.push(message));
    outbox.enqueue(generation, authority, { type: 'status', state: 'connected' });
    let permissionDeliveries = 0;
    for (let acknowledgment = 0; acknowledgment < 12; acknowledgment++) {
        outbox.enqueue(generation, authority, { type: 'upserts', entities: [{ id: 'entity', type: 'Box' }] });
        for (let frame = 0; frame < 30; frame++) {
            outbox.enqueue(generation, authority, { type: 'avatars', avatars: [{ id: 'native-peer', position: { x: acknowledgment, y: 0, z: frame } }] });
            outbox.enqueue(generation, authority, { type: 'permissions', permissions: { connect: true, rez: acknowledgment % 2 === 0, edit: false } });
        }
        assert.equal(delivered.length, acknowledgment + 1);
        assert.ok(outbox.queued <= 3);
        outbox.acknowledge(delivered.at(-1)!.ticket);
        const next = delivered.at(-1)!;
        if (next.event.type === 'permissions') {
            permissionDeliveries++;
            assert.deepEqual(next.event.permissions, { connect: true, rez: acknowledgment % 2 === 0, edit: false });
        }
    }
    assert.ok(permissionDeliveries >= 3, 'permission changes must remain visible despite ongoing world and native pose updates');
});

test('a refreshed snapshot remains after a real entity deletion and session lifecycle barrier', () => {
    const delivered: SessionDelivery[] = [];
    const outbox = new SessionEventOutbox(message => delivered.push(message));
    outbox.enqueue(generation, authority, { type: 'status', state: 'connected' });
    outbox.enqueue(generation, authority, { type: 'avatars', avatars: [{ id: 'old-native', position: { x: 0, y: 0, z: 0 } }] });
    outbox.enqueue(generation, authority, { type: 'remove', ids: ['entity'] });
    outbox.enqueue(generation, { admitted: false, connected: false }, { type: 'status', state: 'error' });
    outbox.enqueue(generation, { admitted: false, connected: false }, { type: 'avatars', avatars: [] });
    for (let index = 0; index < delivered.length; index++) outbox.acknowledge(delivered[index].ticket);
    assert.deepEqual(delivered.map(message => message.event.type), ['status', 'remove', 'status', 'avatars']);
    assert.deepEqual(delivered.at(-1)!.authority, { admitted: false, connected: false });
    assert.deepEqual(delivered.at(-1)!.event, { type: 'avatars', avatars: [] });
});
