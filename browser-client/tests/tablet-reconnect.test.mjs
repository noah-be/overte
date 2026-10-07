// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {BrowserTablet} from '../src/tablet.ts';
import {TabletSession} from '../gateway/tablet.mjs';

// Supply only DOM/service handles; navigation, connection, message validation
// and authority/sequence handling execute the shipping classes unchanged.
function fixture() {
    const descriptors = new Map(['document','HTMLElement'].map(name => [name,Object.getOwnPropertyDescriptor(globalThis,name)]));
    Object.defineProperty(globalThis,'document',{configurable:true,value:{pointerLockElement:null,activeElement:null}});
    Object.defineProperty(globalThis,'HTMLElement',{configurable:true,value:class HTMLElement {}});
    const browser = Object.create(BrowserTablet.prototype);
    const attempts = [], forwarded = [], released = [];
    let revision = 1, active = true, gateway;
    Object.assign(browser,{
        revision:0,sequence:0,frameSequence:0,displayedFrameSequence:0,navigationSequence:0,
        generation:0,connected:false,disposed:false,visible:false,buttons:[],
        element:{hidden:true,style:{}},canvas:{width:480,height:706,style:{},focus(){},hasPointerCapture:()=>true,releasePointerCapture:id=>released.push(id)},
        holder:{getBoundingClientRect:()=>({width:480,height:706})},status:{},
        snapshots:{cancel(){}},fullscreen:{setConnected(){}},
        options:{send(message){attempts.push(message);gateway.receive(message);},onStatus(){},onVisibility(){}}
    });
    function newWorker() {
        gateway?.close();
        gateway = new TabletSession({framePath:'/unused-reconnect-frame.png',
            sendNative:message=>forwarded.push(message),sendBrowser:message=>browser.receive(message),
            getRevision:()=>revision,isActive:()=>active});
    }
    newWorker();
    return {
        browser, attempts, forwarded, released, get gateway(){return gateway;},
        async approve(next) {
            revision=next;active=true;browser.setConnected(true);
            await gateway.receiveNative({type:'tablet',kind:'state',revision,visible:false,loading:false,screen:'Home'});
        },
        disconnect(){active=false;browser.setConnected(false);},
        newWorker,
        close(){gateway.close();for(const [name,descriptor] of descriptors){
            if(descriptor)Object.defineProperty(globalThis,name,descriptor);else Reflect.deleteProperty(globalThis,name);
        }}
    };
}

test('shipping Tablet reconnect on the same worker accepts the first current-revision open',async()=>{
    const f=fixture();try{
        await f.approve(1);f.browser.open();
        for(let i=0;i<9;i++)f.browser.open();
        assert.equal(f.gateway.sequence,10);
        const generation=f.browser.generation;
        f.browser.activePointer={id:7,sequence:3,button:0};
        f.browser.displayedFrameSequence=3;
        f.disconnect();f.disconnect();
        assert.equal(f.browser.sequence,10,'Repeated disconnects retain the command lifetime');
        assert.equal(f.browser.activePointer,undefined);
        assert.deepEqual(f.released,[7]);
        assert.equal(f.browser.visible,false);
        assert.equal(f.browser.revision,0);
        assert.equal(f.browser.navigationSequence,0);
        assert.equal(f.browser.displayedFrameSequence,0);
        if('worldInputReady' in f.browser)assert.equal(f.browser.worldInputReady,false);
        assert.ok(f.browser.generation>generation);
        f.browser.open();assert.equal(f.attempts.length,10,'Disconnected commands do not reach the worker');
        await f.approve(2);
        assert.equal(f.gateway.sequence,10,'Shipping resetRevision preserves the worker command counter');
        assert.doesNotThrow(()=>f.browser.open());
        assert.deepEqual(f.forwarded.at(-1),{type:'tablet',action:'open',revision:2,sequence:11,navigationSequence:11});
        f.disconnect();await f.approve(3);f.browser.open();
        assert.equal(f.forwarded.at(-1).sequence,12);
        assert.equal(f.forwarded.at(-1).revision,3);
    }finally{f.close();}
});

test('same-worker reapproval still refuses old revisions and repeated current commands',async()=>{
    const f=fixture();try{
        await f.approve(1);f.browser.open();const old=f.attempts.at(-1);
        f.disconnect();await f.approve(2);f.browser.open();const current=f.attempts.at(-1);
        const count=f.forwarded.length;
        assert.throws(()=>f.gateway.receive(old),/Stale tablet command/);
        const {revision:oldRevision,...revisionOmittedOpen}=old;
        assert.equal(oldRevision,1);
        assert.throws(()=>f.gateway.receive(revisionOmittedOpen),/Repeated tablet command/);
        assert.throws(()=>f.gateway.receive({...old,sequence:current.sequence+10}),/Stale tablet command/);
        assert.throws(()=>f.gateway.receive(current),/Repeated tablet command/);
        assert.throws(()=>f.gateway.receive({...current,sequence:current.sequence-1}),/Repeated tablet command/);
        assert.equal(f.forwarded.length,count);
        assert.equal(f.gateway.sequence,current.sequence);
        f.browser.open();assert.equal(f.forwarded.at(-1).sequence,current.sequence+1);
    }finally{f.close();}
});

test('a new worker accepts both a retained browser counter and a fresh browser lifetime',async()=>{
    const f=fixture();try{
        await f.approve(1);f.browser.open();f.browser.open();
        f.disconnect();f.newWorker();await f.approve(2);
        assert.equal(f.gateway.sequence,0);
        f.browser.open();assert.equal(f.forwarded.at(-1).sequence,3);
        assert.equal(f.forwarded.at(-1).revision,2);
    }finally{f.close();}
    const fresh=fixture();try{
        await fresh.approve(1);fresh.browser.open();
        assert.equal(fresh.forwarded.at(-1).sequence,1);
        assert.equal(fresh.forwarded.at(-1).revision,1);
    }finally{fresh.close();}
});
