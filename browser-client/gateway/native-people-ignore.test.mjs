// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const source=await readFile(new URL('./native-bridge.js',import.meta.url),'utf8');
function fixture(input=source){
    const start=input.indexOf('poseInterval = Script.setInterval(function () {');
    const end=input.indexOf('        }, 50);',start);
    assert(start>=0&&end>start,'The actual 50ms production avatar callback must be present');
    const ids=['{00000000-0000-0000-0000-000000000000}','{11111111-1111-1111-1111-111111111111}','{22222222-2222-2222-2222-222222222222}','{33333333-3333-3333-3333-333333333333}'];
    const ignored=new Set(),read=[],packets=[],rigCache={};let connected=true,approved=true,callback;
    const context={avatarSampleDiagnostics:null,poseInterval:null,Script:{setInterval(fn,ms){assert.equal(ms,50);callback=fn;return 1;}},
        state(){},flush(){},externalPose(){},location:{get isConnected(){return connected;}},
        get permissionsApproved(){return approved;},
        MyAvatar:{sessionUUID:ids[1]},AvatarList:{getAvatarIdentifiers:()=>ids,
            getAvatar(id){read.push(id);return {id};}},Users:{getIgnoreStatus:id=>ignored.has(id)},rigCache,
        avatarData(id){rigCache[id]={model:'actual-owned-test-rig'};return {id};},send(packet){packets.push(packet);}};
    vm.runInNewContext(input.slice(start,end+'        }, 50);'.length),context);
    return {ids,ignored,read,packets,rigCache,tick:()=>callback(),connected:value=>{connected=value;},approved:value=>{approved=value;}};
}
const emitted=state=>state.packets.at(-1).avatars.map(value=>value.id);

test('actual avatar callback hides ignored peers retained by native People without reading their rig',()=>{
    const f=fixture();f.tick();assert.deepEqual(emitted(f),[f.ids[2],f.ids[3],f.ids[1]]);
    f.ignored.add(f.ids[2]);f.read.length=0;f.tick();
    assert.deepEqual(emitted(f),[f.ids[3],f.ids[1]]);
    assert.deepEqual(f.read,[f.ids[3]],'Ignored native skeleton APIs are never sampled');
    assert.equal(Object.hasOwn(f.rigCache,f.ids[2]),false,'The existing cache ownership prune releases the hidden peer');
    assert.equal(f.packets.at(-1).selfId,f.ids[1]);
});
test('unignore republishes the actual peer; native local self is never removed by peer controls',()=>{
    const f=fixture();f.ignored.add(f.ids[2]);f.ignored.add(f.ids[1]);f.tick();
    assert.deepEqual(emitted(f),[f.ids[3],f.ids[1]]);
    f.ignored.delete(f.ids[2]);f.tick();assert.deepEqual(emitted(f),[f.ids[2],f.ids[3],f.ids[1]]);
    assert(f.read.includes(f.ids[2]));
});
test('existing disconnected and unapproved gates still publish and sample no avatars',()=>{
    const f=fixture();f.connected(false);f.tick();f.connected(true);f.approved(false);f.tick();
    assert.equal(f.packets.length,0);assert.equal(f.read.length,0);assert.equal(Object.keys(f.rigCache).length,0);
});
test('old production single-expression negative control leaks a retained ignored peer',()=>{
    const old=source.replace(' && !Users.getIgnoreStatus(id)','');assert.notEqual(old,source);
    const f=fixture(old);f.ignored.add(f.ids[2]);f.tick();
    assert(emitted(f).includes(f.ids[2]));assert(f.read.includes(f.ids[2]));
});
