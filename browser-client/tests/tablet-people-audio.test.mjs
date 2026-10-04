// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {installPeopleSyntheticAudio,peopleAudioWindow} from './integration/tablet-people-audio.mjs';
function fixture({resume,close}={}){
 const handlers=new Map(),tracks=[],contexts=[];
 class Socket{constructor(){this.listeners=new Map();}addEventListener(type,fn){this.listeners.set(type,fn);}send(){} }
 class Context{
  constructor(){contexts.push(this);this.closed=false;}
  createGain(){return{gain:{value:0},connect(){}};}
  createOscillator(){return{frequency:{value:0},connect(){},start(){},stop(){}};}
  createMediaStreamDestination(){const track={readyState:'live',stop(){this.readyState='ended';}};tracks.push(track);return{stream:{getAudioTracks:()=>[track]}};}
  resume(){return resume?.()??Promise.resolve();}
  close(){this.closed=true;return close?.()??Promise.resolve();}
 }
 const window={WebSocket:Socket,addEventListener:(event,fn)=>handlers.set(event,fn)},navigator={mediaDevices:{}};
 vm.runInNewContext('('+installPeopleSyntheticAudio.toString()+')({frequency:440})',{window,navigator,AudioContext:Context,Float32Array,Int16Array,ArrayBuffer,Error});
 const socket=new window.WebSocket(),probe=window.__peopleSyntheticAudio;
 return{probe,socket,tracks,contexts,getUserMedia:()=>navigator.mediaDevices.getUserMedia({audio:true}),feed:data=>socket.listeners.get('message')({data})};
}
function pcm(hz,amplitude=.03){const samples=new Int16Array(48000*2);for(let i=0;i<48000;i++){const value=Math.round(32767*amplitude*Math.sin(2*Math.PI*hz*i/48000));samples[i*2]=value;samples[i*2+1]=value;}return samples;}
function feed(f,data){for(let n=0;n<data.length;n+=960)f.feed(data.slice(n,n+960).buffer);}
function outgoing(f){for(let n=0;n<10;n++)f.socket.send(new Int16Array([100,100]).buffer);}
test('actual collector accepts fresh opposite-peer tone, rejects partial/stale/missing input and proves spectral suppression without raw audio output',async()=>{
 const f=fixture();await f.getUserMedia();const generation=f.probe.begin('baseline');outgoing(f);
 f.feed(new Int16Array([100,100]).buffer);assert.equal(peopleAudioWindow(f.probe.read(),{phase:'baseline',generation,frequency:659}),false);
 feed(f,pcm(659));const before=f.probe.read();assert(peopleAudioWindow(before,{phase:'baseline',generation,frequency:659}));assert(before.tone659>.029);assert(before.tone440<.00001);
 assert.equal(peopleAudioWindow(before,{phase:'baseline',generation:generation+1,frequency:659}),false);
 const next=f.probe.begin('ignored');outgoing(f);feed(f,pcm(440));const muted=f.probe.read();assert(peopleAudioWindow(muted,{phase:'ignored',generation:next,frequency:659,baseline:before.tone659,suppressed:true}));
 const restore=f.probe.begin('restored');outgoing(f);feed(f,pcm(659));assert(peopleAudioWindow(f.probe.read(),{phase:'restored',generation:restore,frequency:659}));
 f.tracks[0].stop();assert.equal(f.probe.read().activeTracks,0);assert.equal(f.contexts[0].closed,true);f.probe.close();assert.equal(f.probe.read().samples,0);
});
test('zero or unobserved baseline, surviving target tone, disconnected track and wrong sample format cannot prove mute',()=>{
 const row={phase:'ignored',generation:2,samples:48000,rate:48000,activeTracks:1,outgoingNonzeroFrames:30,phaseOutgoingNonzeroFrames:10,tone440:0,tone659:0};
 const options={phase:'ignored',generation:2,frequency:659,baseline:.03,suppressed:true};assert(peopleAudioWindow(row,options));
 for(const modified of [{...row,tone659:.002},{...row,samples:0},{...row,activeTracks:0},{...row,phaseOutgoingNonzeroFrames:0},{...row,rate:24000},{...row,tone659:NaN}])assert.equal(peopleAudioWindow(modified,options),false);
 for(const baseline of [0,null,NaN,Infinity])assert.equal(peopleAudioWindow(row,{...options,baseline}),false);
});
test('pending synthetic resume cancelled by page teardown releases exact track/context and refuses late stream publication',async()=>{
 let release;const f=fixture({resume:()=>new Promise(resolve=>release=resolve)});const request=f.getUserMedia();
 assert.equal(f.tracks[0].readyState,'live');f.probe.close();release();await assert.rejects(request,/lifetime ended/);
 assert.equal(f.tracks[0].readyState,'ended');assert.equal(f.contexts[0].closed,true);assert.equal(f.probe.read().activeTracks,0);
 await assert.rejects(f.getUserMedia(),/admission refused/);
});
test('oversize/misaligned audio cannot populate the bounded private ring',async()=>{
 const f=fixture();await f.getUserMedia();f.probe.begin('baseline');f.feed(new ArrayBuffer(65540));f.feed(new ArrayBuffer(6));assert.equal(f.probe.read().samples,0);
 for(let n=0;n<4;n++)feed(f,pcm(659));assert.equal(f.probe.read().samples,48000);assert(!('samplesPCM' in f.probe.read()));f.probe.close();
});

test('a synchronous context-close failure is explicit and still retires the owned microphone track',async()=>{
 const f=fixture({close:()=>{throw Error('Owned audio context close failed');}});await f.getUserMedia();f.probe.close();
 assert.equal(f.tracks[0].readyState,'ended');assert.equal(f.probe.read().activeTracks,0);assert.equal(f.probe.read().openContexts,0);assert.equal(f.probe.read().cleanupFailed,true);
});
