// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {BrowserFullscreen,type FullscreenDocument,type FullscreenTarget,type FullscreenState} from '../src/fullscreen';
const click={type:'click',isTrusted:true};
function fixture(deadline=8000){
    let enter=0,exit=0;const states:FullscreenState[]=[];
    class Document extends EventTarget implements FullscreenDocument {
        fullscreenEnabled=true;fullscreenElement:Element|null=null;
        async exitFullscreen(){exit++;this.fullscreenElement=null;this.dispatchEvent(new Event('fullscreenchange'));}
    }
    const document=new Document();
    const target:FullscreenTarget={ownerDocument:document,isConnected:true,async requestFullscreen(){enter++;document.fullscreenElement=target as unknown as Element;document.dispatchEvent(new Event('fullscreenchange'));}};
    const control=new BrowserFullscreen(target,state=>states.push(state),deadline);
    return {control,target,document,states,get enter(){return enter;},get exit(){return exit;}};
}
test('a real API call starts in the same synchronous trusted click stack, and actual state governs acknowledgement',async()=>{
    const f=fixture();f.control.setConnected(true);const operation=f.control.invoke(click);assert.equal(f.enter,1);assert.equal(f.control.snapshot().pending,true);
    assert.equal(await operation,true);assert.equal(f.control.snapshot().active,true);assert.equal(await f.control.invoke(click),true);assert.equal(f.exit,1);assert.equal(f.control.snapshot().active,false);f.control.dispose();
});
test('unsupported, detached, disconnected and synthetic input never invoke browser APIs',async()=>{
    const f=fixture();assert.equal(await f.control.invoke(click),false);f.control.setConnected(true);
    for(const event of [{type:'click',isTrusted:false},{type:'keydown',isTrusted:true}])assert.equal(await f.control.invoke(event),false);
    f.document.fullscreenEnabled=false;assert.equal(await f.control.invoke(click),false);f.document.fullscreenEnabled=true;
    Object.assign(f.target,{isConnected:false});assert.equal(await f.control.invoke(click),false);assert.equal(f.enter,0);assert.equal(f.exit,0);f.control.dispose();
});
test('foreign fullscreen remains untouched; a swallowed request is not acknowledged as active',async()=>{
    const f=fixture();f.control.setConnected(true);const foreign={} as Element;f.document.fullscreenElement=foreign;
    assert.equal(await f.control.invoke(click),false);assert.equal(f.exit,0);assert.equal(f.document.fullscreenElement,foreign);
    f.document.fullscreenElement=null;f.target.requestFullscreen=async()=>{};assert.equal(await f.control.invoke(click),false);assert.equal(f.control.snapshot().active,false);f.control.dispose();
});
test('denied and synchronous failure project fixed messages without reflecting browser exceptions',async()=>{
    const f=fixture();f.control.setConnected(true);
    for(const implementation of [()=>Promise.reject(Error('private browser information')),()=>{throw Error('private permission details');}]){
        f.target.requestFullscreen=implementation;assert.equal(await f.control.invoke(click),false);assert(!JSON.stringify(f.states).includes('private'));assert.equal(f.control.snapshot().pending,false);
    }f.control.dispose();
});
test('external Escape/change readback updates actual state; duplicate clicks do not queue another request',async()=>{
    const f=fixture();f.control.setConnected(true);let release!:()=>void;
    f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=()=>{f.document.fullscreenElement=f.target as unknown as Element;resolve();});
    const pending=f.control.invoke(click);assert.equal(await f.control.invoke(click),false);release();assert.equal(await pending,true);
    f.document.fullscreenElement=null;f.document.dispatchEvent(new Event('fullscreenchange'));assert.equal(f.states.at(-1)?.active,false);f.control.dispose();
});
test('disconnect promptly settles owned waiting and cleans a late successful request without changing another target',async()=>{
    const f=fixture();f.control.setConnected(true);let release!:()=>void;
    f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=()=>{f.document.fullscreenElement=f.target as unknown as Element;resolve();});
    const pending=f.control.invoke(click);f.control.setConnected(false);assert.equal(await pending,false);release();await Promise.resolve();await Promise.resolve();
    assert.equal(f.exit,1);assert.equal(f.document.fullscreenElement,null);f.control.dispose();
});
test('replacement controller cannot be exited by an obsolete controller late completion',async()=>{
    const f=fixture();f.control.setConnected(true);let release!:()=>void;
    f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=()=>{f.document.fullscreenElement=f.target as unknown as Element;resolve();});
    const pending=f.control.invoke(click);f.control.dispose();assert.equal(await pending,false);
    const replacement=new BrowserFullscreen(f.target,()=>{});replacement.setConnected(true);
    assert.equal(await replacement.invoke(click),false);release();await Promise.resolve();await Promise.resolve();assert.equal(f.exit,0);assert.equal(replacement.snapshot().active,true);
    assert.equal(await replacement.invoke(click),true);assert.equal(f.exit,1);replacement.dispose();
});
test('deadline bounds owned wait, late failure is consumed, and dispose is idempotent with no observer calls',async()=>{
    const f=fixture(10);f.control.setConnected(true);let reject!:(reason:Error)=>void;
    f.target.requestFullscreen=()=>new Promise<void>((_resolve,no)=>reject=no);
    assert.equal(await f.control.invoke(click),false);assert.equal(f.control.snapshot().pending,true);f.control.dispose();f.control.dispose();
    const count=f.states.length;reject(Error('private late failure'));await Promise.resolve();await Promise.resolve();f.document.dispatchEvent(new Event('fullscreenchange'));assert.equal(f.states.length,count);assert.equal(f.control.snapshot().pending,false);
});
test('closing connection releases only established owned fullscreen and a new connection reads actual state',async()=>{
    const f=fixture();f.control.setConnected(true);assert.equal(await f.control.invoke(click),true);f.control.setConnected(false);await Promise.resolve();await Promise.resolve();assert.equal(f.exit,1);
    f.control.setConnected(true);assert.equal(f.control.snapshot().active,false);assert.equal(await f.control.invoke(click),true);f.control.dispose();await Promise.resolve();assert.equal(f.exit,2);
});

test('an abort inside the state observer still settles waiting promptly and consumes late browser completion',async()=>{
    const f=fixture();let release!:()=>void;f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=()=>{f.document.fullscreenElement=f.target as unknown as Element;resolve();});
    const controller=new BrowserFullscreen(f.target,state=>{if(state.pending)controller.setConnected(false);});controller.setConnected(true);
    assert.equal(await controller.invoke(click),false);release();await Promise.resolve();await Promise.resolve();assert.equal(f.exit,1);controller.dispose();f.control.dispose();
});

test('an observer failure cannot strand the real API promise or its owned cleanup',async()=>{
    const f=fixture();const control=new BrowserFullscreen(f.target,()=>{throw Error('private UI observer failure');});control.setConnected(true);assert.equal(await control.invoke(click),true);control.dispose();await Promise.resolve();assert.equal(f.exit,1);f.control.dispose();
});

// Same-target replacement must inherit cleanup, not the old request's acknowledgement.
test('a disconnected replacement releases an established owned fullscreen after the old controller retires',async()=>{
    const f=fixture();f.control.setConnected(true);assert.equal(await f.control.invoke(click),true);
    const replacement=new BrowserFullscreen(f.target,()=>{});replacement.setConnected(true);f.control.dispose();
    assert.equal(f.exit,0);replacement.setConnected(false);await Promise.resolve();await Promise.resolve();
    assert.equal(f.exit,1);assert.equal(f.document.fullscreenElement,null);replacement.dispose();
});

test('disposing a replacement before an old pending enter completes cannot strand fullscreen',async()=>{
    const f=fixture();f.control.setConnected(true);let release!:()=>void;
    f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=()=>{f.document.fullscreenElement=f.target as unknown as Element;f.document.dispatchEvent(new Event('fullscreenchange'));resolve();});
    const pending=f.control.invoke(click);f.control.dispose();assert.equal(await pending,false);
    const replacement=new BrowserFullscreen(f.target,()=>{});replacement.setConnected(true);replacement.dispose();
    release();await Promise.resolve();await Promise.resolve();
    assert.equal(f.exit,1);assert.equal(f.document.fullscreenElement,null);
});

test('a current replacement observes the pending request settle and owns subsequent disconnect cleanup',async()=>{
    const f=fixture();f.control.setConnected(true);let release!:()=>void;
    f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=()=>{f.document.fullscreenElement=f.target as unknown as Element;f.document.dispatchEvent(new Event('fullscreenchange'));resolve();});
    const pending=f.control.invoke(click);f.control.dispose();assert.equal(await pending,false);
    const states:FullscreenState[]=[];const replacement=new BrowserFullscreen(f.target,state=>states.push(state));replacement.setConnected(true);
    assert.equal(states.at(-1)?.pending,true);release();await Promise.resolve();await Promise.resolve();
    assert.equal(states.at(-1)?.pending,false);assert.equal(states.at(-1)?.active,true);assert.equal(f.exit,0);
    replacement.setConnected(false);await Promise.resolve();assert.equal(f.exit,1);replacement.dispose();
});

test('replacement cleanup does not exit an actual foreign fullscreen element on old completion',async()=>{
    const f=fixture();f.control.setConnected(true);let release!:()=>void;
    f.target.requestFullscreen=()=>new Promise<void>(resolve=>release=resolve);
    const pending=f.control.invoke(click);f.control.dispose();assert.equal(await pending,false);
    const replacement=new BrowserFullscreen(f.target,()=>{});replacement.setConnected(true);replacement.dispose();
    const foreign={} as Element;f.document.fullscreenElement=foreign;release();await Promise.resolve();await Promise.resolve();
    assert.equal(f.exit,0);assert.equal(f.document.fullscreenElement,foreign);
});

test('an obsolete controller cannot clear the current replacement connection or release its owned fullscreen',async()=>{
    const f=fixture();f.control.setConnected(true);assert.equal(await f.control.invoke(click),true);
    const replacement=new BrowserFullscreen(f.target,()=>{});replacement.setConnected(true);
    f.control.setConnected(false);f.control.dispose();assert.equal(f.exit,0);assert.equal(replacement.snapshot().active,true);
    replacement.dispose();await Promise.resolve();assert.equal(f.exit,1);
});

test('a target adopted into another document refuses before requesting an unobserved fullscreen context',async()=>{
    const f=fixture(),other=fixture();f.control.setConnected(true);Object.assign(f.target,{ownerDocument:other.document});
    assert.equal(f.control.snapshot().available,false);assert.equal(await f.control.invoke(click),false);assert.equal(f.enter,0);
    f.control.dispose();other.control.dispose();
});
