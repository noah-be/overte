// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const source = (await readFile(new URL('./native-push-to-talk.js', import.meta.url), 'utf8')) + '\n'
    + (await readFile(new URL('./native-world.js', import.meta.url), 'utf8')) + '\n'
    + await readFile(new URL('./native-bridge.js', import.meta.url), 'utf8');
function fixture() {
    let socket, tabletSend, navigationReceive, clock = 1000;
    const sent = [], timers = new Map(), callbacks = [];
    const location = { href: 'hifi://127.0.0.2:45102', domainID: '{11111111-1111-1111-1111-111111111111}', isConnected: true };
    const context = { BROWSER_GATEWAY: { url: 'ws://local/native', token: 'test-only', domain: location.href,
        tablet: { scriptURL: 'file:///fixture/helper.js' }, navigation:{channel:'browser-places-test'} },
        Messages:{subscribe(){},unsubscribe(){},sendLocalMessage(){},messageReceived:{connect(callback){navigationReceive=callback;},disconnect(){}}},
        Uuid:{generate:()=>'{12345678-abcd-1234-5678-123456789abc}'},
        Date: { now: () => clock }, print() {}, Audio: {}, Users: { canKick: false },
        WebSocket: class { constructor() { socket = this; this.readyState = 1; } send(value) { sent.push(JSON.parse(value)); } close() {} },
        MyAvatar: { position: { x: 0, y: 1, z: 0 }, orientation: { x: 0, y: 0, z: 0, w: 1 }, sessionUUID: '{22222222-2222-2222-2222-222222222222}', setGravity() {} },
        AvatarList: { getAvatarIdentifiers: () => [] }, Assets: { getAsset(_request, callback) { callbacks.push(callback); } },
        Entities: { findEntities: () => [], getEntityProperties: () => {},
            ...Object.fromEntries(['canRez', 'canRezTmp', 'canRezAvatarEntities', 'canViewAssetURLs', 'canAdjustLocks', 'canWriteAssets', 'canReplaceContent', 'canGetAndSetPrivateUserData'].map(name => [name, () => name === 'canViewAssetURLs'])) },
        Window: { domainConnectionRefused: { connect() {} } },
        Script: { include() {}, setInterval(callback, delay) { timers.set(delay, callback); return delay; },
            clearInterval() {}, scriptEnding: { connect() {} }, btoa: value => value.toString('base64') },
        createBrowserTablet(config) { tabletSend = config.send; return { setAuthority() {}, close() {} }; },
    };
    Object.defineProperty(context, 'location', { get: () => location, set() {} });
    vm.runInNewContext(source, context); socket.onopen(); timers.get(50)();
    const revision = sent.find(value => value.type === 'permissions').permissionRevision;
    const receive = message => socket.onmessage({ data: JSON.stringify(message) });
    receive({ type: 'permissionsAccepted', permissionRevision: revision }); timers.get(50)(); sent.length = 0;
    return { sent, timers, callbacks, location, receive, tabletSend, revision, navigationReceive, advance: milliseconds => { clock += milliseconds; } };
}

test('queued native domain data is discarded when authority changes before the engine timer drains it', () => {
    const f = fixture();
    f.receive({ type: 'asset', requestId: 'owned-asset', url: 'atp:/fixture.png' });
    f.callbacks[0](null, { response: Buffer.from('actual asset bytes') });
    f.tabletSend({ type: 'tablet', kind: 'clipboard', revision: f.revision, requestId: 1, text: 'old domain selection' });
    assert.deepEqual(f.sent, [], 'Qt/native callbacks do not directly write the WebSocket');
    f.location.href = 'hifi://127.0.0.3:45302'; f.location.domainID = '{33333333-3333-3333-3333-333333333333}';
    f.timers.get(50)();
    assert.equal(f.sent.some(value => ['asset', 'tablet', 'avatars', 'pose', 'entities', 'entityUpdates'].includes(value.type)), false);
    assert.equal(f.sent.find(value => value.type === 'permissions').domain, f.location.href);
});

test('native engine drains only unexpired challenges and preserves them across domain revocation', () => {
    const f = fixture(); const nonce = '0123456789abcdef0123456789abcdef';
    f.receive({ type: 'nativePing', nonce, deadline: 2000 }); f.advance(1000); f.timers.get(50)();
    assert.equal(f.sent.some(value => value.type === 'nativePong'), false, 'A queued challenge cannot be echoed after its strict deadline');
    f.receive({ type: 'nativePing', nonce, deadline: 4000 });
    f.location.isConnected = false; f.timers.get(50)();
    assert.equal(f.sent.filter(value => value.type === 'nativePong').length, 1, 'Domain-independent round trips remain available during connection transitions');
    assert.equal(f.sent.find(value => value.type === 'nativePong').nonce, nonce);
});

test('a burst of genuine sized asset callbacks exceeding the byte budget fails closed without partial delivery', () => {
    const f = fixture(); const response = Buffer.alloc(16 * 1024 * 1024, 65);
    for (let index = 0; index < 3; index++) f.receive({ type: 'asset', requestId: 'asset-' + index, url: 'atp:/fixture-' + index });
    for (const callback of f.callbacks) callback(null, { response });
    assert.deepEqual(f.sent, []);
    f.timers.get(50)();
    assert.equal(f.sent.some(value => value.type === 'asset'), false, 'World/asset messages are never silently delivered as an incomplete queue');
    assert.match(f.sent.find(value => value.type === 'state' && value.state === 'error').message, /bounded queue/);
});

test('unbounded callback traffic cannot exceed the native message-count limit', () => {
    const f = fixture();
    for (let index = 0; index < 129; index++) f.receive({ type: 'nativePing', nonce: index.toString(16).padStart(32, '0'), deadline: 30000 });
    assert.deepEqual(f.sent, []);
    f.timers.get(50)();
    assert.equal(f.sent.some(value => value.type === 'nativePong'), false);
    assert.match(f.sent.find(value => value.type === 'state' && value.state === 'error').message, /bounded queue/);
});


test('owner-local Places requests wait for the engine timer and cannot escape a revoked authority', () => {
    const f=fixture();
    f.navigationReceive('browser-places-test',JSON.stringify({kind:'target',address:'overte://allowed'}),'sender',false);
    f.timers.get(50)();
    assert.equal(f.sent.some(message=>message.type==='navigationRequest'),false,'Nonlocal mixer messages cannot navigate this visitor');
    f.navigationReceive('browser-places-test',JSON.stringify({kind:'target',address:'overte://allowed'}),'sender',true);
    assert.equal(f.sent.some(message=>message.type==='navigationRequest'),false,'Qt Messages callbacks cannot directly send socket output');
    f.timers.get(50)();
    const request=f.sent.find(message=>message.type==='navigationRequest');
    assert.equal(request.permissionRevision,f.revision);assert.equal(request.nonce,'12345678-abcd-1234-5678-123456789abc');
    f.sent.length=0;
    f.navigationReceive('browser-places-test',JSON.stringify({kind:'history',direction:'back'}),'sender',true);
    f.location.isConnected=false;f.timers.get(50)();
    assert.equal(f.sent.some(message=>message.type==='navigationHistoryRequest'),false,'Revocation discards queued old-domain navigation');
});
