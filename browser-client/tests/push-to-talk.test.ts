// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {BrowserAudio} from '../src/audio';
import {BrowserPushToTalk} from '../src/push-to-talk';
import {PushToTalkSession} from '../gateway/push-to-talk.mjs';
import {pushToTalkCommand,pushToTalkState} from '../shared/push-to-talk.mjs';
const nativeSource=readFileSync(new URL('../gateway/native-push-to-talk.js',import.meta.url),'utf8');
const state=(sequence=0,enabled=true,held=false,muted=true,permissionRevision=1)=>({type:'pushToTalkState',version:1,permissionRevision,sequence,enabled,held,muted});
function browser(){
    let active=true,armed=false,gate=false;const sent:unknown[]=[];
    const p=new BrowserPushToTalk({current:r=>active&&r===1,armed:()=>armed,send:m=>sent.push(m),gate:v=>gate=v,changed:()=>{}});
    p.setAuthority(1,true);
    return {p,sent,gate:()=>gate,arm(v=true){armed=v;p.refreshMicrophone();},revoke(){active=false;p.setAuthority(1,false);}};
}
function native(){
    let active=true,enabled=true,held=false,muted=true,authority='guest|fixed-domain';const calls:string[]=[],out:unknown[]=[];
    const signals=Object.fromEntries(['pushToTalkDesktopChanged','pushingToTalkChanged','mutedChanged'].map(name=>[name,new Set<()=>void>()]));
    const emit=(name:string)=>{for(const fn of signals[name])fn();};
    const audio={
        get pushToTalkDesktop(){return enabled;},set pushToTalkDesktop(v){enabled=v;emit('pushToTalkDesktopChanged');},
        get pushingToTalk(){return held;},set pushingToTalk(v){calls.push('held:'+v);held=v;emit('pushingToTalkChanged');},
        get muted(){return muted;},set muted(v){calls.push('muted:'+v);muted=v;
            // Exact relevant f91 setMutedDesktop rule: unmute while not held disables PTT.
            if(!v&&!held)audio.pushToTalkDesktop=false;emit('mutedChanged');},
        ...Object.fromEntries(Object.entries(signals).map(([name,set])=>[name,{connect(fn:()=>void){set.add(fn);},disconnect(fn:()=>void){set.delete(fn);}}]))
    };
    const ctx=vm.createContext({});vm.runInContext(nativeSource+';this.create=createBrowserPushToTalk;',ctx);
    const p=ctx.create({audio,authority:()=>authority,current:(r:number)=>active&&r===1,send:(v:unknown)=>out.push(JSON.parse(JSON.stringify(v)))});
    p.setAuthority(1,true);p.poll();calls.length=0;
    return {p,audio,out,calls,signals,changeAuthority(){authority='guest|replacement';},revoke(){active=false;p.setAuthority(1,false);}};
}
test('explicit permission precedes held request; native ACK precedes local PCM and release closes gate before send',()=>{
    const f=browser();f.p.receive(state());assert.equal(f.p.press(),true);assert.deepEqual(f.sent,[]);assert.equal(f.gate(),false);
    f.arm();f.p.press();assert.equal(f.gate(),false);assert.equal(f.sent.length,1);f.p.press();assert.equal(f.sent.length,1);
    f.p.receive(state(1,true,true,false));assert.equal(f.gate(),true);f.p.release();assert.equal(f.gate(),false);assert.equal(f.sent.length,2);
    f.p.receive(state(1,true,true,false));assert.equal(f.gate(),false);f.p.receive(state(2));assert.equal(f.gate(),false);
});
test('revision, connection and mode ownership reject stale enable ACKs and revoke held permission',()=>{
    const f=browser();f.arm();f.p.receive(state());f.p.press();f.p.receive(state(1,true,true,false,2));assert.equal(f.gate(),false);
    f.p.receive(state(1,true,true,false));assert.equal(f.gate(),true);f.revoke();assert.equal(f.gate(),false);
    f.p.receive(state(1,true,true,false));assert.equal(f.gate(),false);f.p.close();assert.equal(f.gate(),false);
});
test('ordinary microphone waits known native actual unmute; stale mode-off packet cannot open held PCM',()=>{
    const f=browser();f.arm();assert.equal(f.gate(),false);f.p.receive(state(0,false,false,false));assert.equal(f.gate(),true);
    assert.equal(f.p.press(),false);f.p.receive(state());f.p.press();assert.equal(f.gate(),false);
    f.p.receive(state(0,false,false,false));assert.equal(f.gate(),false);f.arm(false);assert.equal(f.gate(),false);
});
test('native adapter arms without disabling real PTT; held flag is written before unmute and genuine release restores mute',()=>{
    const f=native();f.p.setMuted(false);f.p.poll();assert.equal(f.audio.pushToTalkDesktop,true);assert.equal(f.audio.muted,true);
    f.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});f.p.poll();
    assert.equal(f.audio.pushingToTalk,true);assert.equal(f.audio.muted,false);assert.equal(f.audio.pushToTalkDesktop,true);
    assert.deepEqual(f.calls.slice(-2),['held:true','muted:false']);assert.deepEqual(f.out.at(-1),state(1,true,true,false));
    f.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:false});f.p.poll();assert.equal(f.audio.muted,true);assert.equal(f.audio.pushingToTalk,false);
});
test('original mute-false negative control disables native PTT, unlike armed adapter',()=>{
    const old=native();old.audio.muted=false;assert.equal(old.audio.pushToTalkDesktop,false);
    const fixed=native();fixed.p.setMuted(false);assert.equal(fixed.audio.pushToTalkDesktop,true);
});
test('native signals cannot send from Qt callback; disarm, stale command, revocation and close cannot hold native input',()=>{
    const f=native();const count=f.out.length;f.audio.pushToTalkDesktop=false;assert.equal(f.out.length,count);
    f.audio.pushToTalkDesktop=true;f.p.setMuted(false);f.p.receive({type:'pushToTalk',version:1,permissionRevision:2,sequence:1,held:true});assert.equal(f.audio.pushingToTalk,false);
    f.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});f.revoke();assert.equal(f.audio.pushingToTalk,false);assert.equal(f.audio.muted,true);
    f.p.poll();assert.equal(f.out.length,count);f.p.close();f.p.close();assert(Object.values(f.signals).every(s=>s.size===0));
});
test('gateway independently requires exact approval, microphone intent and latest native effective hold',()=>{
    let connected=true,approved=true,muted=false,revision=1;const sent:unknown[]=[],browser:unknown[]=[];
    const p=new PushToTalkSession({connected:()=>connected,approved:()=>approved,muted:()=>muted,revision:()=>revision,sendNative:(m:unknown)=>sent.push(m),sendBrowser:(m:unknown)=>browser.push(m)});
    assert.equal(p.allowsAudio(),false);p.receiveNative(state());p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});assert.equal(p.allowsAudio(),false);
    p.receiveNative(state(1,true,true,false));assert.equal(p.allowsAudio(),true);p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:false});assert.equal(p.allowsAudio(),false);
    p.receiveNative(state(1,true,true,false));assert.equal(p.allowsAudio(),false);p.receiveNative(state(2,false,false,false));assert.equal(p.allowsAudio(),true);
    muted=true;assert.equal(p.allowsAudio(),false);muted=false;approved=false;assert.equal(p.allowsAudio(),false);approved=true;revision=2;assert.equal(p.allowsAudio(),false);
    connected=false;p.reset();assert.equal(p.allowsAudio(),false);
});
test('strict versioned DTOs clone only bounded booleans and refuse invalid ACK semantics',()=>{
    const value={...state(),token:'PRIVATE'};assert.equal(Object.hasOwn(pushToTalkState(value),'token'),false);
    for(const bad of [state(0,false,true,false),state(-1),state(0,true,false,true,0),{...state(),enabled:1},{...state(),version:2}])assert.throws(()=>pushToTalkState(bad));
    assert.throws(()=>pushToTalkCommand({...state(),type:'pushToTalk'}));assert.throws(()=>pushToTalkCommand({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:'true'}));
});

test('native user mute while a hold remains active is a valid actual state and gates PCM; disabling mode preserves native mute',()=>{
 const f=browser();f.arm();f.p.receive(state());f.p.press();f.p.receive(state(1,true,true,false));assert.equal(f.gate(),true);
 f.p.receive(state(1,true,true,true));assert.equal(f.gate(),false);
 const n=native();n.p.setMuted(false);n.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});n.p.poll();
 n.audio.muted=true;n.p.poll();assert.equal(pushToTalkState(n.out.at(-1)).muted,true);
 n.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:false});n.audio.pushToTalkDesktop=false;n.p.poll();assert.equal(n.audio.muted,true);
});

test('validated Tablet view pause cancels held intent without closing explicit microphone permission or renewing old ACK',()=>{
 let muted=false;const p=new PushToTalkSession({connected:()=>true,approved:()=>true,muted:()=>muted,revision:()=>1,sendNative:()=>{},sendBrowser:()=>{}});
 p.receiveNative(state());p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});p.receiveNative(state(1,true,true,false));assert.equal(p.allowsAudio(),true);
 p.cancel();assert.equal(p.allowsAudio(),false);p.receiveNative(state(1,true,true,false));assert.equal(p.allowsAudio(),false);assert.equal(muted,false);
 const n=native();n.p.setMuted(false);n.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});n.p.release();n.p.poll();assert.equal(n.audio.pushingToTalk,false);assert.equal(n.audio.muted,true);
 n.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:true});n.p.poll();assert.equal(n.audio.pushingToTalk,true,'Retained explicit arm permits a later fresh physical hold');
});
test('command gaps and unsafe final hold are refused; reserved final sequence remains available to release',()=>{
 let muted=false;const sent:unknown[]=[];const p=new PushToTalkSession({connected:()=>true,approved:()=>true,muted:()=>muted,revision:()=>1,sendNative:(v:unknown)=>sent.push(v),sendBrowser:()=>{}});
 p.receiveNative(state());p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:true});assert.deepEqual(sent,[]);
 const internal=p as unknown as {sequence:number};internal.sequence=Number.MAX_SAFE_INTEGER-1;
 p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:Number.MAX_SAFE_INTEGER,held:true});assert.deepEqual(sent,[]);
 p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:Number.MAX_SAFE_INTEGER,held:false});assert.equal(sent.length,1);
});

test('native authority identity change mutes and releases without publishing stale state or recapturing scope',()=>{
 const f=native();f.p.setMuted(false);f.p.receive({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});f.p.poll();const count=f.out.length;
 f.changeAuthority();f.p.setAuthority(1,true);assert.equal(f.audio.pushingToTalk,false);assert.equal(f.audio.muted,true);f.p.poll();assert.equal(f.out.length,count);
});
test('actual BrowserAudio keeps explicitly granted microphone alive while worklet/network both gate and discard late PCM',async()=>{
 const keys=['window','AudioContext','AudioWorkletNode','navigator'],original=new Map(keys.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 let node:any,getUserMediaCalls=0,trackStops=0;const pcmSent:ArrayBuffer[]=[],commands:unknown[]=[];
 const track={readyState:'live',getSettings:()=>({echoCancellation:true,noiseSuppression:true,autoGainControl:true}),onended:null as (()=>void)|null,stop(){trackStops++;}};
 class Context {
  audioWorklet={addModule:async()=>{}};destination={};resume=async()=>{};close=async()=>{};
  createGain(){return{gain:{value:0},connect(){return{disconnect(){}};},disconnect(){}};}
  createMediaStreamSource(){return{connect(target:unknown){return target;},disconnect(){}};}
 }
 class Worklet {port={postMessage(_value:unknown){},onmessage:null as ((value:any)=>void)|null};constructor(){node=this;}connect(){return this;}disconnect(){}}
 Object.defineProperty(globalThis,'window',{configurable:true,value:{AudioContext:Context,isSecureContext:true}});
 Object.defineProperty(globalThis,'AudioContext',{configurable:true,value:Context});Object.defineProperty(globalThis,'AudioWorkletNode',{configurable:true,value:Worklet});
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:async()=>{getUserMediaCalls++;return{getTracks:()=>[track],getAudioTracks:()=>[track]};}}}});
 const audio=new BrowserAudio(data=>pcmSent.push(data),()=>{});const p=new BrowserPushToTalk({current:r=>r===1,armed:()=>!audio.muted,send:m=>commands.push(m),gate:v=>audio.setTransmitEnabled(v),changed:()=>{}});
 try {
  p.setAuthority(1,true);p.receive(state());await audio.start();assert.equal(getUserMediaCalls,0);
  assert.equal(await audio.enableMicrophone(),true);p.refreshMicrophone();assert.equal(getUserMediaCalls,1);
  const deliver=()=>node.port.onmessage({data:{type:'microphone',buffer:new ArrayBuffer(1920)}});
  deliver();assert.equal(pcmSent.length,0);p.press();deliver();assert.equal(pcmSent.length,0);
  p.receive(state(1,true,true,false));deliver();assert.equal(pcmSent.length,1);p.release();deliver();assert.equal(pcmSent.length,1);
  assert.equal(audio.muted,false);assert.equal(trackStops,0);assert.equal(getUserMediaCalls,1);assert.equal(commands.length,2);
 } finally {p.close();await audio.dispose();for(const key of keys){const descriptor=original.get(key);if(descriptor)Object.defineProperty(globalThis,key,descriptor);else Reflect.deleteProperty(globalThis,key);}}
 assert.equal(trackStops,1);
});
