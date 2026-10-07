// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BrowserSession, parseServerMessage } from './session.ts';

test('real entity and avatar protocol messages retain native properties', () => {
    const value = {type:'entities',entities:[{id:'entity',type:'Model',modelURL:'atp:/test.glb',position:{x:1,y:2,z:3}}]};
    assert.deepEqual(parseServerMessage(JSON.stringify(value)), value);
    assert.deepEqual(parseServerMessage('{"type":"avatars","avatars":[{"id":"native","position":{"x":0,"y":1,"z":0}}]}').type, 'avatars');
});
test('malformed gateway state, identity and world data are rejected', () => {
    for (const message of [null, [], {}, {type:'unrecognized'}, {type:'state',state:'ready'},
        {type:'state',state:'connected',sessionId:'../../other'}, {type:'entities',entities:[{}]},
        {type:'avatars',avatars:[{id:'native',position:{x:'0',y:0,z:0}}]},
        {type:'pose',position:{x:0,y:null,z:0}}, {type:'error',message:42}]) {
        assert.throws(() => parseServerMessage(JSON.stringify(message)));
    }
});

test('incremental world messages preserve real entity changes and validate deletions', () => {
    const value = { type: 'entityUpdates', entities: [{ id: 'changed', type: 'Model', position: { x: 12, y: 3, z: 9 } }], removed: ['gone'] };
    assert.deepEqual(parseServerMessage(JSON.stringify(value)), value);
    for (const removed of [undefined, null, {}, [3], ['x'.repeat(129)]]) {
        assert.throws(() => parseServerMessage(JSON.stringify({ ...value, removed })));
    }
});

test('native navigation carries an exact authority revision, nonce and bounded finite pose', () => {
    const request = { type: 'poseRequest', nonce: '12345678-abcd-1234-5678-123456789abc', permissionRevision: 3,
        position: { x: 12, y: 2, z: -4 }, orientation: { x: 0, y: 0, z: 0, w: 1 } };
    assert.deepEqual(parseServerMessage(JSON.stringify(request)), request);
    for (const change of [{ nonce: '../foreign-session' }, { permissionRevision: 0 }, { permissionRevision: 1.5 },
        { position: { x: 32768, y: 0, z: 0 } }, { position: { x: -32768, y: 0, z: 0 } }, { position: { x: 0, y: null, z: 0 } },
        { orientation: { x: 0, y: 0, z: 0, w: 0 } }, { orientation: { x: 0, y: 0, z: 0, w: 2 } }]) {
        assert.throws(() => parseServerMessage(JSON.stringify({ ...request, ...change })), /navigation/);
    }
});

test('Places handoffs carry bounded Overte addresses or exact history directions', () => {
    const request = {type:'navigation',nonce:'12345678-abcd-1234-5678-123456789abc',permissionRevision:3,domain:'overte://overte_hub/1,2,3/0,0,0,1'};
    assert.deepEqual(parseServerMessage(JSON.stringify(request)), request);
    assert.equal(parseServerMessage(JSON.stringify({...request,type:'navigationHistory',direction:'back'})).type, 'navigationHistory');
    for (const domain of ['https://overte_hub', 'overte:///missing', 'overte://user:secret@overte_hub', 'overte://overte_hub#secret', 'overte://overte_hub?token=secret', 'x'.repeat(1025)]) {
        assert.throws(() => parseServerMessage(JSON.stringify({...request,domain})));
    }
    for (const change of [{nonce:'old'}, {permissionRevision:0}, {permissionRevision:1.5}, {type:'navigationHistory',direction:'sideways'}]) {
        assert.throws(() => parseServerMessage(JSON.stringify({...request,...change})));
    }
});
test('actual avatar joint names retain model-unit poses with bounded consistent arrays', () => {
    const avatar = {id:'native',position:{x:0,y:1,z:0},skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst',
        jointNames:['body','face','Hips'],jointRotations:Array.from({length:3},()=>({x:0,y:0,z:0,w:1})),
        jointTranslations:[{x:0,y:0,z:0},{x:0,y:0,z:0},{x:0,y:101.3,z:0}]};
    const packet = (value:unknown) => JSON.stringify({type:'avatars',avatars:[value]});
    assert.deepEqual(parseServerMessage(packet(avatar)),{type:'avatars',avatars:[avatar]});
    for (const change of [{jointNames:undefined}, {jointNames:['Hips']}, {jointNames:['x'.repeat(257),'face','Hips']},
        {jointRotations:[{x:0,y:0,z:0,w:0}]}, {jointTranslations:[{x:0,y:null,z:0}]},
        {skeletonOffset:{x:0,y:101,z:0}}, {skeletonModelURL:42}]) assert.throws(()=>parseServerMessage(packet({...avatar,...change})),/avatar/);
});
test('visitor preferences preserve only safe bookmark/home fields with an exact revision', () => {
    const packet = {type:'visitorPreferences',permissionRevision:2,bookmarks:[{name:'Hub',address:'overte://overte_hub'}],home:'overte://overte_hub'};
    assert.deepEqual(parseServerMessage(JSON.stringify({...packet,accountToken:'synthetic unrelated field'})),packet);
    for (const change of [{permissionRevision:0},{bookmarks:[{name:'private',address:'file:///operator'}]},
        {home:'https://operator.example'},{bookmarks:Array.from({length:101},(_,index)=>({name:`Place ${index}`,address:'overte://overte_hub'}))}]) {
        assert.throws(()=>parseServerMessage(JSON.stringify({...packet,...change})));
    }
});

test('visitor persona packets carry only bounded avatar fields and exact native authority',()=>{
    const packet={type:'visitorPersona',permissionRevision:2,displayName:'Überte 世界 👋',avatarScale:1.5,
        avatarURL:'https://content.overte.org/avatar.fst',avatarFavorites:[]};
    assert.deepEqual(parseServerMessage(JSON.stringify({...packet,accountToken:'synthetic unrelated field'})),packet);
    for(const change of [{permissionRevision:0},{displayName:'x'.repeat(257)},{avatarURL:'file:///operator/profile'},
        {avatarScale:0},{avatarScale:1001},{avatarFavorites:[{name:'Private',avatarURL:'qrc:/operator/file',avatarScale:1}]}]) {
        assert.throws(()=>parseServerMessage(JSON.stringify({...packet,...change})));
    }
});
test('an oversized join is refused before any browser socket or old-session cleanup',()=>{
    const session=new BrowserSession({message:()=>{},audio:()=>{},closed:()=>{},error:()=>{}});
    // This Node check deliberately has no window/WebSocket implementation:
    // admission-size refusal must happen before interacting with browser state.
    assert.throws(()=>session.join('overte://'+'x'.repeat(192*1024),'Visitor'),/192 KiB/);
    assert.throws(()=>session.join('overte://world','Visitor',undefined,{avatarURL:'file:///operator/profile'}));
});
