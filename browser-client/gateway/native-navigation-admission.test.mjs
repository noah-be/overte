// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { once } from 'node:events';
import vm from 'node:vm';
import WebSocket, { WebSocketServer } from 'ws';
import { validateNativeNavigation, admittedNavigationTarget } from './navigation.mjs';
import { NativeHeartbeat } from './socket-heartbeat.mjs';
import { validateVisitorPreferences } from '../shared/visitor-preferences.mjs';
import { acceptedNativePersona } from './visitor-persona.mjs';
const domain = 'overte://127.0.0.2:45102';
const nonce = '11111111-1111-1111-1111-111111111111';
const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate) {
    for (let index = 0; index < 100; index++) {
        if (predicate()) return;
        await new Promise(resolve => setTimeout(resolve, 5));
    }
    assert.fail('Production native navigation did not reach the expected state');
}

// The actual production native handler receives real WebSocket packets. Only
// external directory resolution and native process cleanup are controlled.
async function harness(t, resolve = async () => ({ nativeDomain: 'overte://203.0.113.9:40102' })) {
    const source = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
    const start = source.indexOf("nativeServer.on('connection'"), end = source.indexOf('const heartbeat =', start);
    assert(start >= 0 && end > start);
    const server = createServer(), nativeServer = new WebSocketServer({ server });
    const sockets = new Set(), messages = [], events = [];
    const browser = { readyState: WebSocket.OPEN };
    const session = {
        id: 'fixture-session', token: 'fixture-token', browser, closed: false,
        connected: true, permissionsApproved: true, permissionRevision: 7,
        muted: true, pendingAssets: new Map(), personaOrigins: new Set(['https://content.overte.org']), waitForDomain() {},
        close() { this.closed = true; this.permissionsApproved = false; this.connected = false; events.push('revoke'); return Promise.resolve(); }
    };
    const context = vm.createContext({ process:{env:{}}, nativeServer, sockets, sessions: new Map([[session.id, session]]),
        setTimeout, clearTimeout, Date, Buffer, NativeHeartbeat, equal: (a, b) => a === b,
        domains: [domain], publicPlaces: ['overte_hub'], validateNativeNavigation, validateVisitorPreferences, acceptedNativePersona,
        admittedNavigationTarget: (address, configuration) => admittedNavigationTarget(address, { ...configuration, resolve }),
        send(target, message) {
            if (target === browser) { events.push(message.type); messages.push(JSON.parse(JSON.stringify(message))); }
            else if (target.readyState === WebSocket.OPEN) target.send(JSON.stringify(message));
        }
    });
    vm.runInContext(source.slice(source.indexOf('function avatarFlowEnabled('), source.indexOf('function avatarFlowDistance(')) + source.slice(start, end), context);
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    const native = new WebSocket(`ws://127.0.0.1:${server.address().port}`);
    const nativeMessages = []; native.on('message', data => nativeMessages.push(JSON.parse(data.toString())));
    await once(native, 'open'); native.send(JSON.stringify({ type: 'nativeHello', token: session.token }));
    await until(() => nativeMessages.some(message => message.type === 'mute'));
    let received=0;session.native.on('message',()=>received++);
    t.after(async () => {
        session.closed = true; native.terminate(); for (const socket of sockets) socket.terminate();
        await new Promise(done => nativeServer.close(done)); await new Promise(done => server.close(done));
    });
    const send = message => native.send(JSON.stringify({ type: 'navigationRequest', nonce, permissionRevision: 7, address: domain, ...message }));
    return { native, nativeMessages, session, messages, events, send, get received(){return received;} };
}

test('managed Places navigation synchronously revokes its old worker before requesting a fresh browser join', async t => {
    const state = await harness(t); state.send({ address: domain + '/5,1.5,3/0,0,0,1' });
    await until(() => state.messages.some(message => message.type === 'navigation'));
    assert.deepEqual(state.events, ['revoke', 'navigation']);
    assert.equal(state.session.closed, true);
    assert.deepEqual(state.messages[0], { type: 'navigation', nonce, permissionRevision: 7, domain: domain + '/5,1.5,3/0,0,0,1' });
});

test('unsupported Places destination warns while preserving the active world and permission approval', async t => {
    const state = await harness(t); state.send({ address: 'overte://203.0.113.10:40102' });
    await until(() => state.messages.some(message => message.type === 'warning'));
    assert.match(state.messages[0].message, /not enabled/);
    assert.equal(state.session.closed, false); assert.equal(state.session.connected, true); assert.equal(state.session.permissionsApproved, true);
    assert.deepEqual(state.events, ['warning']);
});

for(const address of ['file:///visitor/private-scene.json','http://unsupported-world.invalid','']){
    test(`ordinary unsupported native Places input warns without disconnecting (${address||'empty address'})`,async t=>{
        let directoryLookups=0;
        const state=await harness(t,async()=>{directoryLookups++;return {nativeDomain:'overte://203.0.113.9:40102'};});
        const originalNative=state.session.native;
        state.send({address});await until(()=>state.messages.some(message=>message.type==='warning'));
        assert.equal(state.session.closed,false);assert.equal(state.session.connected,true);assert.equal(state.session.permissionsApproved,true);
        assert.equal(state.session.native,originalNative);assert.equal(state.native.readyState,WebSocket.OPEN);
        assert.equal(directoryLookups,0,'Unsupported schemes and an empty target never trigger domain admission or external resolution');
        assert.deepEqual(state.events,['warning']);assert.equal(state.messages.some(message=>message.type==='navigation'),false);
        state.send({type:'navigationHistoryRequest',direction:'back'});await until(()=>state.messages.some(message=>message.type==='navigationHistory'));
        assert.equal(state.session.closed,false,'The same authenticated native socket remains usable after the ordinary input refusal');
    });
}

test('history direction and exact approval revision reach the browser without replacing the native worker', async t => {
    const state = await harness(t); state.send({ type: 'navigationHistoryRequest', direction: 'back' });
    await until(() => state.messages.length === 1);
    assert.deepEqual(state.messages[0], { type: 'navigationHistory', nonce, permissionRevision: 7, direction: 'back' });
    assert.equal(state.session.closed, false);
    state.send({ type: 'navigationHistoryRequest', direction: 'forward' }); await until(() => state.messages.length === 2);
    assert.equal(state.messages[1].direction, 'forward'); assert.equal(state.session.closed, false);
});

for (const malformed of [{ nonce: 'invalid' }, { permissionRevision: 6 }, { type: 'navigationHistoryRequest', direction: 'reload' },{address:null},{address:'x'.repeat(1025)}]) {
    test(`invalid native navigation authority/history closes the bridge (${JSON.stringify(malformed,(_key,value)=>typeof value==='string'&&value.length>128?'[oversized text]':value)})`, async t => {
        const state = await harness(t); state.send(malformed); await once(state.native, 'close'); await until(() => state.session.closed);
        assert.equal(state.messages.some(message => ['navigation', 'navigationHistory'].includes(message.type)), false);
        assert.equal(state.session.closed, true);
        assert.match(state.messages.find(message => message.state === 'error').message, /invalid message data/);
    });
}

for (const change of ['closed', 'revision', 'approval', 'native']) {
    test(`deferred directory resolution cannot navigate after ${change} authority changes`, async t => {
        let release, called = false;
        const resolution = new Promise(resolve => { release = resolve; });
        const state = await harness(t, async () => { called = true; return resolution; });
        state.send({ address: 'overte://overte_hub' }); await until(() => called);
        if (change === 'closed') state.session.close();
        else if (change === 'revision') state.session.permissionRevision++;
        else if (change === 'approval') state.session.permissionsApproved = false;
        else state.session.native = {};
        release({ nativeDomain: 'overte://203.0.113.9:40102' }); await until(() => state.session.navigationPending === false); await tick();
        assert.equal(state.messages.some(message => message.type === 'navigation'), false);
        assert.equal(state.messages.some(message => message.type === 'warning'), false);
        if (change !== 'closed') assert.equal(state.session.closed, false);
    });
}

test('approved native bookmarks forward only validated plain preferences and discard unrelated native envelope fields',async t=>{
    const state=await harness(t);state.send({type:'visitorPreferences',bookmarks:[{name:' Managed viewpoint ',address:'hifi://127.0.0.2:45102/5,1.5,3/0,0,0,1'}],home:domain,privateNativeField:'fixture-secret'});
    await until(()=>state.messages.some(message=>message.type==='visitorPreferences'));
    assert.deepEqual(state.messages[0],{type:'visitorPreferences',permissionRevision:7,bookmarks:[{name:'Managed viewpoint',address:domain+'/5,1.5,3/0,0,0,1'}],home:domain});
    assert.equal(state.session.closed,false);assert.equal(JSON.stringify(state.messages).includes('fixture-secret'),false);
});
for(const revoked of ['revision','approval'])test(`native preference delivery is suppressed after ${revoked} changes`,async t=>{
    const state=await harness(t);if(revoked==='approval')state.session.permissionsApproved=false;
    const before=state.received;state.send({type:'visitorPreferences',permissionRevision:revoked==='revision'?6:7,bookmarks:[{name:'Managed viewpoint',address:domain}]});
    await until(()=>state.received>before);await tick();assert.equal(state.messages.length,0);assert.equal(state.session.closed,false);
});
for(const unsafe of [
    {name:'Unsafe file',address:'file:///fixture-private-file'},
    {name:'Credential address',address:'overte://fixture-user:fixture-secret@127.0.0.2:45102'},
    {name:'Extra bookmark fields',address:domain,privateField:'fixture-secret'}
])test(`unsafe native bookmark (${unsafe.name}) warns without leaking its data or disconnecting`,async t=>{
    const state=await harness(t);state.send({type:'visitorPreferences',bookmarks:[unsafe]});
    await until(()=>state.messages.some(message=>message.type==='warning'));
    assert.match(state.messages[0].message,/Existing saved browser preferences were preserved/);
    assert.equal(state.messages.some(message=>message.type==='visitorPreferences'),false);
    assert.equal(JSON.stringify(state.messages).includes('fixture-secret'),false);assert.equal(JSON.stringify(state.messages).includes('fixture-private-file'),false);
    assert.equal(state.session.closed,false);assert.equal(state.session.connected,true);assert.equal(state.session.permissionsApproved,true);
});


test('approved native persona forwards its bounded visitor data without native envelope secrets',async t=>{
    const state=await harness(t);
    const persona={displayName:'Überte 世界 👋',avatarURL:'https://content.overte.org/Kim.fst',avatarScale:1.25,
        avatarFavorites:[{name:'Favorite',avatarURL:'https://content.overte.org/Kim.fst',avatarScale:1.25}]};
    state.send({type:'visitorPersona',...persona,privateNativeField:'fixture-secret'});
    await until(()=>state.messages.some(message=>message.type==='visitorPersona'));
    assert.deepEqual(state.messages,[{type:'visitorPersona',permissionRevision:7,...persona}]);
    assert.equal(state.session.closed,false);assert.equal(JSON.stringify(state.messages).includes('fixture-secret'),false);
});
for(const revoked of ['revision','approval','connection'])test(`native persona cannot update browser storage after ${revoked} changes`,async t=>{
    const state=await harness(t);
    if(revoked==='approval')state.session.permissionsApproved=false;
    if(revoked==='connection')state.session.connected=false;
    const before=state.received;
    state.send({type:'visitorPersona',permissionRevision:revoked==='revision'?6:7,displayName:'Unsafe stale rename'});
    await until(()=>state.received>before);await tick();
    assert.deepEqual(state.messages,[]);assert.equal(state.session.closed,false);
});
for(const unsafe of [
    {name:'Credential URL',avatarURL:'https://fixture-user:fixture-secret@content.overte.org/Kim.fst',avatarScale:1},
    {name:'Unapproved origin',avatarURL:'https://fixture-private.invalid/Kim.fst',avatarScale:1},
    {name:'Executable wearable',avatarURL:'https://content.overte.org/Kim.fst',avatarScale:1,avatarEntities:[{properties:{type:'Model',modelURL:'https://content.overte.org/hat.fbx',script:'fixture-secret'}}]}
])test(`unsafe native persona favorite (${unsafe.name}) preserves stored favorites and the active socket`,async t=>{
    const state=await harness(t);
    state.send({type:'visitorPersona',displayName:'Safe partial update',avatarFavorites:[unsafe]});
    await until(()=>state.messages.some(message=>message.type==='warning'));
    assert.deepEqual(state.messages[0],{type:'visitorPersona',permissionRevision:7,displayName:'Safe partial update'});
    assert.equal(state.messages.some(message=>message.avatarFavorites!==undefined),false);
    assert.match(state.messages[1].message,/Saved browser favorites were preserved/);
    assert.equal(JSON.stringify(state.messages).includes('fixture-secret'),false);
    assert.equal(JSON.stringify(state.messages).includes('fixture-private'),false);
    assert.equal(state.session.closed,false);assert.equal(state.session.connected,true);assert.equal(state.native.readyState,WebSocket.OPEN);
});
