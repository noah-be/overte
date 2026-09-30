// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

test('native AvatarManager null self key never becomes a phantom peer', async () => {
    const timers = new Map(), sent = [];
    const own = '{11111111-1111-1111-1111-111111111111}', peer = '{22222222-2222-2222-2222-222222222222}';
    let socket;
    const avatar = { displayName: 'Native visitor', position: { x: 0, y: 1, z: 0 }, orientation: { x: 0, y: 0, z: 0, w: 1 }, scale: 1 };
    const context = {
        BROWSER_GATEWAY: { url: 'ws://127.0.0.1/native', token: 'test-only', domain: 'overte://test' },
        WebSocket: class { constructor() { socket = this; this.readyState = 1; } send(value) { sent.push(JSON.parse(value)); } },
        MyAvatar: { ...avatar, sessionUUID: own, setGravity(value) { this.gravity = value; } }, Audio: {}, print() {},
        AvatarList: { getAvatarIdentifiers: () => [null, 'null', '{00000000-0000-0000-0000-000000000000}', own, peer], getAvatar: () => avatar },
        Entities: { findEntities: () => [], canRez: () => false, canRezTmp: () => false, canRezAvatarEntities: () => true,
            canViewAssetURLs: () => true, canAdjustLocks: () => false, canWriteAssets: () => false,
            canReplaceContent: () => false, canGetAndSetPrivateUserData: () => false },
        Menu: { triggerOption(option) { context.quitOption = option; } },
        Users: { canKick: false }, Window: { domainConnectionRefused: { connect() {} } },
        Script: { setInterval(callback, delay) { timers.set(delay, callback); return delay; }, scriptEnding: { connect() {} } },
    };
    const nativeLocation = { isConnected: true, href: 'overte://test' };
    Object.defineProperty(context, 'location', { get: () => nativeLocation, set() {} });
    vm.runInNewContext(await readFile(new URL('./native-bridge.js', import.meta.url), 'utf8'), context);
    socket.onopen();
    assert.equal(context.MyAvatar.gravity, 0, 'Native gravity must not move a browser-controlled avatar');
    timers.get(50)();
    assert.equal(sent.filter(message => message.type === 'avatars').length, 0, 'No world data is exposed before permission approval');
    timers.get(500)();
    assert.equal(sent.filter(message => message.type === 'entities').length, 0);
    assert.equal(sent.filter(message => message.type === 'state' && message.state === 'connected').length, 0);
    assert.equal(sent.find(message => message.type === 'permissions').permissions.id_can_kick, false);
    const initialRevision = sent.find(message => message.type === 'permissions').permissionRevision;
    socket.onmessage({ data: JSON.stringify({ type: 'permissionsAccepted', permissionRevision: initialRevision }) });
    socket.onmessage({ data: JSON.stringify({ type: 'pose', position: { x: 1, y: 2, z: 3 }, orientation: avatar.orientation, velocity: { x: 1, y: -1, z: 3 } }) });
    assert.deepEqual(JSON.parse(JSON.stringify(context.MyAvatar.velocity)), { x: 0, y: 0, z: 0 }, 'Native replication cannot integrate browser velocity twice');
    timers.get(50)();
    const snapshot = sent.find(message => message.type === 'avatars');
    assert.equal(snapshot.selfId, own);
    assert.deepEqual(snapshot.avatars.map(value => value.id), [peer, own]);
    assert.equal(snapshot.avatars.filter(value => value.id === own).length, 1);
    assert.equal(context.Audio.muted, true);
    timers.get(500)(); sent.length = 0;
    timers.get(500)();
    assert.equal(sent.filter(message => message.type === 'entities').length, 0, 'Unchanged stable world snapshots are deduplicated');
    nativeLocation.isConnected = false; timers.get(500)();
    nativeLocation.isConnected = true; timers.get(500)();
    const reconnectRevision = sent.filter(message => message.type === 'permissions').at(-1).permissionRevision;
    socket.onmessage({ data: JSON.stringify({ type: 'permissionsAccepted', permissionRevision: reconnectRevision }) });
    sent.length = 0; timers.get(500)();
    assert.equal(sent.filter(message => message.type === 'entities').length, 1, 'Identical world data is resent after reconnect to restore assets');
    socket.onmessage({ data: JSON.stringify({ type: 'mute', muted: false }) });
    assert.equal(context.Audio.muted, false);
    sent.length = 0;
    nativeLocation.href = 'overte://other-domain';
    timers.get(50)();
    assert.equal(sent.filter(message => message.type === 'avatars').length, 0, 'Same-permission redirects must revoke data approval');
    assert.equal(context.Audio.muted, true, 'A domain redirect must immediately mute native input');
    assert.equal(sent.find(message => message.type === 'permissions').domain, 'overte://other-domain');
    socket.onmessage({ data: JSON.stringify({ type: 'mute', muted: false }) });
    assert.equal(context.Audio.muted, true, 'Unmute is rejected while the new domain is unapproved');
    socket.onmessage({ data: JSON.stringify({ type: 'permissionsAccepted', permissionRevision: initialRevision, muted: false }) });
    assert.equal(context.Audio.muted, true, 'An old approval cannot unmute a newer domain');
    sent.length = 0; timers.get(50)();
    assert.equal(sent.filter(message => message.type === 'avatars').length, 0, 'Stale acknowledgments cannot release new-domain world data');
    socket.onmessage({ data: JSON.stringify({ type: 'shutdown' }) });
    assert.equal(context.quitOption, 'Quit', 'Leaving must run the normal native quit/disconnect lifecycle');
    assert.equal(context.Audio.muted, true);
});
