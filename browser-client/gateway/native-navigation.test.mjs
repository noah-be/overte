// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { nativePoseRequest } from './validation.mjs';

async function fixture() {
    const timers = new Map(), messages = []; let socket;
    const location = { isConnected: true, href: 'overte://127.0.0.2:45102', domainID: randomUUID() };
    const avatar = { position: { x: 0, y: 1, z: 0 }, orientation: { x: 0, y: 0, z: 0, w: 1 }, sessionUUID: randomUUID(), setGravity() {} };
    const context = { BROWSER_GATEWAY: { url:'ws://127.0.0.1/native', token:'synthetic', domain:location.href },
        WebSocket:class { constructor(){socket=this;this.readyState=1;} send(value){messages.push(JSON.parse(value));} },
        MyAvatar:avatar, Audio:{}, Uuid:{generate:()=>'{'+randomUUID().toUpperCase()+'}'}, print(){}, Users:{canKick:false},
        Entities:Object.fromEntries(['canRez','canRezTmp','canRezAvatarEntities','canViewAssetURLs','canAdjustLocks','canWriteAssets','canReplaceContent','canGetAndSetPrivateUserData'].map(key=>[key,()=>key==='canViewAssetURLs'])),
        AvatarList:{getAvatarIdentifiers:()=>[]}, Window:{domainConnectionRefused:{connect(){}}},
        Script:{setInterval(callback,delay){timers.set(delay,callback);return delay;},scriptEnding:{connect(){}}} };
    Object.defineProperty(context,'location',{get:()=>location,set(){}});
    vm.runInNewContext((await readFile(new URL('./native-push-to-talk.js',import.meta.url),'utf8'))+'\n'+(await readFile(new URL('./native-world.js',import.meta.url),'utf8'))+'\n'+await readFile(new URL('./native-bridge.js',import.meta.url),'utf8'),context);
    const receive = message=>{socket.onmessage({data:JSON.stringify(message)});timers.get(50)();};
    socket.onopen();timers.get(50)();
    const revision=messages.find(message=>message.type==='permissions').permissionRevision;
    receive({type:'permissionsAccepted',permissionRevision:revision}); messages.length=0;
    return {avatar,location,messages,receive,revision,timers};
}

test('actual native bridge preserves an external teleport before an old browser pose and requires the exact revision/nonce acknowledgement',async()=>{
    const f=await fixture(), old={type:'pose',position:{x:1,y:1,z:0},orientation:{x:0,y:0,z:0,w:1}};
    f.receive(old);f.avatar.position={x:20,y:4,z:-6};
    f.receive(old);
    const request=f.messages.find(message=>message.type==='poseRequest');
    assert.ok(request);assert.equal(request.position.x,20);assert.equal(f.avatar.position.x,20);
    assert.match(request.nonce,/^[a-f0-9-]{36}$/);
    f.receive({type:'poseAccepted',nonce:randomUUID(),permissionRevision:f.revision});f.receive(old);
    assert.equal(f.avatar.position.x,20,'An unrelated acknowledgement cannot resume stale browser movement');
    f.receive({type:'poseAccepted',nonce:request.nonce,permissionRevision:f.revision+1});f.receive(old);
    assert.equal(f.avatar.position.x,20,'An unapproved authority revision cannot resume replication');
    f.receive({type:'poseAccepted',nonce:request.nonce,permissionRevision:f.revision});
    f.receive({...old,position:{x:21,y:4,z:-6}});
    assert.equal(f.avatar.position.x,21,'The browser resumes normal movement after applying the exact teleport');
});

test('newer native teleport supersedes old nonce; disconnect prevents old-authority navigation release',async()=>{
    const f=await fixture();f.avatar.position={x:10,y:1,z:0};f.timers.get(50)();
    const first=f.messages.find(message=>message.type==='poseRequest');
    f.avatar.position={x:30,y:1,z:0};f.receive({type:'poseAccepted',nonce:first.nonce,permissionRevision:f.revision});
    const second=f.messages.filter(message=>message.type==='poseRequest').at(-1);
    assert.notEqual(second.nonce,first.nonce);assert.equal(second.position.x,30);
    f.receive({type:'pose',position:{x:0,y:1,z:0},orientation:{x:0,y:0,z:0,w:1}});
    assert.equal(f.avatar.position.x,30,'A replaced request remains pending after its predecessor acknowledgement');
    f.location.isConnected=false;f.timers.get(50)();
    f.receive({type:'poseAccepted',nonce:second.nonce,permissionRevision:f.revision});
    assert.equal(f.avatar.position.x,30);
});

test('gateway navigation validation requires finite real pose and canonical revision-bound nonce',()=>{
    const value={type:'poseRequest',nonce:randomUUID(),permissionRevision:3,position:{x:2,y:4,z:1},orientation:{x:0,y:0,z:0,w:1}};
    assert.deepEqual(nativePoseRequest(value,3),value);
    assert.throws(()=>nativePoseRequest(value,4));
    assert.throws(()=>nativePoseRequest({...value,nonce:'{'+value.nonce+'}'},3));
    assert.throws(()=>nativePoseRequest({...value,position:{x:Infinity,y:4,z:1}},3));
});
