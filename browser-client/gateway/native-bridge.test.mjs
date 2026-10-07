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
    let entities = [];
    let nameCalls=0;
    const jointRotation={x:0,y:0,z:0,w:1,toJSON(){throw Error('Qt wrapper must be cloned');}};
    const jointTranslation={x:1,y:2,z:3,toJSON(){throw Error('Qt wrapper must be cloned');}};
    const avatar = { displayName: 'Native visitor', position: { x: 0, y: 1, z: 0 }, orientation: { x: 0, y: 0, z: 0, w: 1 }, scale: 1, skeletonModelURL:'resource:/meshes/defaultAvatar_full.fst', skeletonOffset:{x:0,y:.25,z:0},
        getJointNames(){nameCalls++;return ['Hips','Head'];},getJointRotations(){return [jointRotation,jointRotation];},
        getJointTranslations(){return [jointTranslation,jointTranslation];} };
    const context = {
        BROWSER_GATEWAY: { url: 'ws://127.0.0.1/native', token: 'test-only', domain: 'overte://test' },
        WebSocket: class { constructor() { socket = this; this.readyState = 1; } send(value) { sent.push(JSON.parse(value)); } },
        MyAvatar: { ...avatar, sessionUUID: own, setGravity(value) { this.gravity = value; } }, Audio: {}, print() {},
        AvatarList: { getAvatarIdentifiers: () => [null, 'null', '{00000000-0000-0000-0000-000000000000}', own, peer], getAvatar: () => avatar },
        Entities: { findEntities: () => entities.map(entity => entity.id), getEntityProperties: id => entities.find(entity => entity.id === id),
            canRez: () => false, canRezTmp: () => false, canRezAvatarEntities: () => true,
            canViewAssetURLs: () => true, canAdjustLocks: () => false, canWriteAssets: () => false,
            canReplaceContent: () => false, canGetAndSetPrivateUserData: () => false },
        Menu: { triggerOption(option) { context.quitOption = option; } },
        Users: { canKick: false, getIgnoreStatus: () => false }, Window: { domainConnectionRefused: { connect() {} } },
        Script: { setInterval(callback, delay) { timers.set(delay, callback); return delay; }, scriptEnding: { connect() {} } },
    };
    const nativeLocation = { isConnected: true, href: 'overte://test', domainID: '{33333333-3333-3333-3333-333333333333}' };
    Object.defineProperty(context, 'location', { get: () => nativeLocation, set() {} });
    vm.runInNewContext((await readFile(new URL('./native-push-to-talk.js', import.meta.url), 'utf8')) + '\n' + (await readFile(new URL('./native-world.js', import.meta.url), 'utf8')) + '\n' + await readFile(new URL('./native-bridge.js', import.meta.url), 'utf8'), context);
    socket.onopen();
    timers.get(50)();
    const nonce = '0123456789abcdef0123456789abcdef';
    socket.onmessage({ data: JSON.stringify({ type: 'nativePing', nonce, deadline: Date.now() + 30000 }) });
    assert.equal(sent.some(message => message.type === 'nativePong'), false, 'Qt socket callbacks never directly send a post-handshake response');
    timers.get(50)();
    assert.equal(sent.find(message => message.type === 'nativePong').nonce, nonce, 'The actual native engine responds before domain permission approval');
    const replies = sent.filter(message => message.type === 'nativePong').length;
    socket.onmessage({ data: JSON.stringify({ type: 'nativePing', nonce: 'invalid' }) });
    assert.equal(sent.filter(message => message.type === 'nativePong').length, replies, 'Malformed application challenges are not echoed');
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
    assert.deepEqual(snapshot.avatars[0].jointNames,['Hips','Head']);
    assert.deepEqual(snapshot.avatars[0].jointTranslations,[{x:1,y:2,z:3},{x:1,y:2,z:3}]);
    assert.deepEqual(snapshot.avatars[0].jointRotations,[{x:0,y:0,z:0,w:1},{x:0,y:0,z:0,w:1}]);
    assert.deepEqual(snapshot.avatars[0].skeletonOffset,{x:0,y:.25,z:0});
    const calls=nameCalls; timers.get(50)(); assert.equal(nameCalls,calls,'Joint names remain cached per actual avatar/model');
    avatar.skeletonModelURL='https://example.invalid/changed.fst'; timers.get(50)();
    assert.ok(nameCalls>calls,'Changing the actual model invalidates its native joint-name mapping');
    assert.equal(context.Audio.muted, true);
    timers.get(500)(); sent.length = 0;
    timers.get(500)();
    assert.equal(sent.filter(message => message.type === 'entities').length, 0, 'Unchanged stable world snapshots are deduplicated');
    entities = [{ id: own, type: 'Box', age: 10, ageAsText: '10 seconds', renderInfo: { vertices: 10 },
        position: { x: 0, y: 0, z: 0 }, userData: '{"worldProperty":"preserved"}' },
        { id: peer, type: 'Model', modelURL: 'atp:/actual-model.glb', position: { x: 1, y: 0, z: 0 } }];
    sent.length = 0; timers.get(500)();
    let update = sent.find(message => message.type === 'entityUpdates');
    assert.equal(update.entities.length, 2, 'New entities are delivered as upserts after the initial snapshot');
    assert.equal(update.entities[0].age, 10, 'Change payloads retain all native properties');
    assert.equal(update.entities[0].userData, entities[0].userData);
    entities[0].age = 11; entities[0].ageAsText = '11 seconds'; entities[0].renderInfo = { vertices: 20 };
    sent.length = 0; timers.get(500)();
    assert.equal(sent.filter(message => message.type === 'entityUpdates').length, 0, 'Aging/render diagnostics do not resend a static world');
    entities[0].position = { x: 2, y: 0, z: 0 };
    sent.length = 0; timers.get(500)();
    update = sent.find(message => message.type === 'entityUpdates');
    assert.equal(update.entities.length, 1, 'One real movement sends only the changed entity');
    assert.equal(update.entities[0].position.x, 2); assert.equal(update.entities[0].age, 11);
    entities = [];
    sent.length = 0; timers.get(500)();
    update = sent.find(message => message.type === 'entityUpdates');
    assert.deepEqual(update.entities, []); assert.deepEqual(update.removed, [own, peer], 'Leaving the query range removes old entities');
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
    const redirectedRevision = sent.find(message => message.type === 'permissions').permissionRevision;
    socket.onmessage({ data: JSON.stringify({ type: 'mute', muted: false }) });
    assert.equal(context.Audio.muted, true, 'Unmute is rejected while the new domain is unapproved');
    socket.onmessage({ data: JSON.stringify({ type: 'permissionsAccepted', permissionRevision: initialRevision, muted: false }) });
    assert.equal(context.Audio.muted, true, 'An old approval cannot unmute a newer domain');
    sent.length = 0; timers.get(50)();
    assert.equal(sent.filter(message => message.type === 'avatars').length, 0, 'Stale acknowledgments cannot release new-domain world data');
    socket.onmessage({ data: JSON.stringify({ type: 'permissionsAccepted', permissionRevision: redirectedRevision }) });
    nativeLocation.domainID = '{44444444-4444-4444-4444-444444444444}';
    sent.length = 0; timers.get(50)();
    assert.equal(sent.find(message => message.type === 'permissions').domainId, '44444444-4444-4444-4444-444444444444', 'Actual DomainHandler identity changes require a fresh approval even with the same display alias');
    assert.equal(sent.filter(message => message.type === 'avatars').length, 0);
    timers.get(50)();
    socket.onmessage({ data: JSON.stringify({ type: 'shutdown' }) });
    assert.equal(context.quitOption, 'Quit', 'Leaving must run the normal native quit/disconnect lifecycle');
    assert.equal(context.Audio.muted, true);
});
