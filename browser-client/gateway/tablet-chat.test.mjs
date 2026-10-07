// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {nativeChatMessage} from './tablet-chat.mjs';
const sender='12345678-1234-1234-1234-123456789abc';
test('chat observation preserves actual bounded UTF-8 delivery and rejects malformed native records',()=>{
    const message={sequence:1,channel:'domain',text:'Hello 世界 👋',displayName:'Visitor',senderId:sender};assert.deepEqual(nativeChatMessage(message),message);
    assert.equal(nativeChatMessage({...message,text:'👋'.repeat(2048)}).text.length,4096);
    for(const patch of [{sequence:0},{channel:'private'},{text:'👋'.repeat(2049)},{displayName:'x'.repeat(129)},{senderId:'invalid'}])assert.throws(()=>nativeChatMessage({...message,...patch}));
});
test('actual native helper observes only approved genuine in-range message-mixer chat without adding a send API',async()=>{
    const callbacks=new Set(),subscriptions=[],output=[];let active=false;
    const context=vm.createContext({Messages:{subscribe:name=>subscriptions.push(name),unsubscribe:name=>subscriptions.splice(subscriptions.indexOf(name),1),messageReceived:{connect:fn=>callbacks.add(fn),disconnect:fn=>callbacks.delete(fn)}},Date,MyAvatar:{position:{x:0,y:0,z:0}},Vec3:{distance:(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)}});
    vm.runInContext(await readFile(new URL('./native-tablet-chat.js',import.meta.url),'utf8'),context);
    const helper=context.createBrowserTabletChat({isActive:()=>active,send:value=>output.push(value)});
    const emit=(patch={},localOnly=false)=>{for(const fn of callbacks)fn('chat',JSON.stringify({action:'send_chat_message',message:'Hello 世界 👋',displayName:'Native peer',channel:'domain',position:{x:0,y:0,z:0},...patch}),sender,localOnly);};
    emit();assert.equal(output.length,0);active=true;emit();assert.equal(output[0].text,'Hello 世界 👋');assert.equal(output[0].senderId,sender);
    emit({},true);emit({forApp:'Floof'});emit({message:'👋'.repeat(2049)});emit({action:'typing'});emit({channel:'local',position:{x:20.01,y:0,z:0}});assert.equal(output.length,1);
    emit({channel:'local',position:{x:20,y:0,z:0}});assert.equal(output.length,2);active=false;emit();assert.equal(output.length,2);
    helper.close();helper.close();assert.equal(callbacks.size,0);assert.equal(subscriptions.length,0);assert.equal(typeof helper.send,'undefined');
});
