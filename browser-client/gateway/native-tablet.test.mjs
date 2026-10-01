// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

function signal(){const handlers=new Set();return {connect:fn=>handlers.add(fn),disconnect:fn=>handlers.delete(fn),emit:value=>{for(const fn of handlers)fn(value);},get count(){return handlers.size;}};}
test('actual native Tablet helper loads all installed standard apps and gates captures, inputs and teardown by authority',async()=>{
    const output=[],qml=[],loads=[],timers=[],screens=[];
    const fromQml=signal(),screenChanged=signal(),mutedChanged=signal();let windowClosed=0,cleared=0;
    const nativeTablet={screenChanged,loadQMLSource:source=>screens.push(source),returnToPreviousApp:()=>screens.push('back')};
    const context=vm.createContext({Tablet:{getTablet:()=>nativeTablet},OverlayWindow:function(){this.fromQml=fromQml;this.sendToQml=item=>qml.push(item);this.close=()=>windowClosed++;},Audio:{muted:true,mutedChanged},Script:{load:url=>loads.push(url),setTimeout:(fn,delay)=>{if(delay===0)fn();},setInterval:fn=>{timers.push(fn);return 1;},clearInterval:()=>cleared++},Date});
    vm.runInContext(await readFile(new URL('./native-tablet.js',import.meta.url),'utf8'),context);
    const helper=context.createBrowserTablet({qmlURL:'file:///private/capture.qml',framePath:'/private/tablet.png',defaultScriptsURL:'file:///installed/defaultScripts.js',send:item=>output.push(item)});
    assert.deepEqual(loads,['file:///installed/defaultScripts.js']);
    helper.receive({action:'open',revision:1});timers[0]();assert.equal(qml.length,0);
    helper.setAuthority(1,true);helper.receive({action:'open',revision:1});timers[0]();
    assert.deepEqual(screens,['hifi/tablet/TabletHome.qml']);assert.equal(qml.at(-1).kind,'capture');
    const capture=qml.at(-1);fromQml.emit({kind:'frame',revision:1,sequence:capture.sequence,width:480,height:706,surface:'tablet',saved:true});
    timers[0]();assert.equal(output.at(-1).kind,'frameReady');
    const count=qml.length;timers[0]();assert.equal(qml.length,count,'no overwriting unacknowledged frame');
    helper.receive({action:'frameAck',revision:1,frameSequence:capture.sequence});timers[0]();assert.equal(qml.length,count+1);
    helper.receive({action:'input',revision:2,event:'key',key:'A'});assert.equal(qml.length,count+1,'stale input refused');
    helper.setAuthority(2,false);const sent=output.length;fromQml.emit({kind:'frame',revision:1,sequence:2,saved:true});timers[0]();assert.equal(output.length,sent,'revoked authority cannot expose stale frames');
    helper.close();helper.close();assert.equal(windowClosed,1);assert.equal(cleared,1);assert.equal(fromQml.count,0);assert.equal(screenChanged.count,0);assert.equal(mutedChanged.count,0);
});

test('native worker avoids duplicate world draw jobs, retains HUD, bounds stalled captures and permits explicit retry',async()=>{
    const output=[],qml=[],timers=[];let now=1000;
    const jobs={DrawOpaqueDeferred:{enabled:true},DrawTransparentDeferred:{enabled:true},RenderHUDLayer:{enabled:true}};
    const fromQml=signal(),screenChanged=signal();
    const context=vm.createContext({Tablet:{getTablet:()=>({screenChanged,loadQMLSource:()=>{}})},
        OverlayWindow:function(){this.fromQml=fromQml;this.sendToQml=item=>qml.push(item);this.close=()=>{};},
        Audio:{muted:true},Render:{getConfig:path=>jobs[path.split('.').at(-1)]},
        Script:{load:()=>{},setTimeout:(fn,delay)=>{if(delay===0)fn();},setInterval:fn=>{timers.push(fn);return 1;},clearInterval:()=>{}},Date:{now:()=>now}});
    vm.runInContext(await readFile(new URL('./native-tablet.js',import.meta.url),'utf8'),context);
    const helper=context.createBrowserTablet({qmlURL:'file:///capture.qml',framePath:'/private/frame',defaultScriptsURL:'file:///defaultScripts.js',send:item=>output.push(item)});
    assert.equal(jobs.DrawOpaqueDeferred.enabled,false);assert.equal(jobs.DrawTransparentDeferred.enabled,false);
    assert.equal(jobs.RenderHUDLayer.enabled,true,'Qt/HUD capture render path remains available');
    helper.setAuthority(1,true);helper.receive({action:'open',revision:1});timers[0]();
    const first=qml.at(-1);assert.equal(first.kind,'capture');
    now+=30001;timers[0]();timers[0]();assert.match(output.find(item=>item.kind==='error').message,/30 seconds.*retry/);
    const count=qml.length;now+=100000;timers[0]();assert.equal(qml.length,count,'stalled grab is not repeatedly queued');
    fromQml.emit({kind:'frame',revision:1,sequence:first.sequence,saved:false,cancelled:true});assert.notEqual(output.at(-1).kind,'frameReady','late timed-out capture is discarded');
    helper.receive({action:'home',revision:1});timers[0]();assert.equal(qml.at(-1).kind,'capture');assert.ok(qml.at(-1).sequence>first.sequence);
    helper.close();assert.equal(jobs.DrawOpaqueDeferred.enabled,true);assert.equal(jobs.DrawTransparentDeferred.enabled,true);assert.equal(jobs.RenderHUDLayer.enabled,true);
});

test('rapid Home/open/back/revocation retain one GPU grab and stale callbacks cannot save or forward prior screens',async()=>{
    const qml=[],output=[],timers=[];let now=1000;
    const fromQml=signal(),screenChanged=signal();
    const context=vm.createContext({Tablet:{getTablet:()=>({screenChanged,loadQMLSource:()=>{},returnToPreviousApp:()=>{}})},OverlayWindow:function(){this.fromQml=fromQml;this.sendToQml=value=>qml.push(value);this.close=()=>{};},Audio:{muted:true},Script:{load:()=>{},setTimeout:(fn,delay)=>{if(delay===0)fn();},setInterval:fn=>timers.push(fn),clearInterval:()=>{}},Date:{now:()=>now}});
    vm.runInContext(await readFile(new URL('./native-tablet.js',import.meta.url),'utf8'),context);
    const helper=context.createBrowserTablet({qmlURL:'file:///capture.qml',framePath:'/private/frame',defaultScriptsURL:'file:///defaultScripts.js',send:value=>output.push(value)});
    helper.setAuthority(1,true);helper.receive({action:'open',revision:1});timers[0]();const first=qml.find(value=>value.kind==='capture');
    for(let index=0;index<100;index++){helper.receive({action:index%2?'home':'back',revision:1});timers[0]();}
    assert.equal(qml.filter(value=>value.kind==='capture').length,1,'Repeated navigation does not create more in-flight grabs');
    helper.setAuthority(2,true);helper.receive({action:'open',revision:2});timers[0]();assert.equal(qml.filter(value=>value.kind==='capture').length,1);
    fromQml.emit({kind:'frame',revision:1,sequence:first.sequence,saved:false,cancelled:true});timers[0]();
    const next=qml.at(-1);assert.equal(next.kind,'capture');assert.equal(next.revision,2);assert.notEqual(next.sequence,first.sequence);
    assert.equal(output.filter(value=>value.kind==='frameReady').length,0,'Previous authority cannot display an old screen');
    // A slow but observed legitimate cold capture is accepted within the30s budget.
    now+=13000;timers[0]();assert.equal(qml.filter(value=>value.kind==='capture').length,2);
    fromQml.emit({kind:'frame',revision:2,sequence:next.sequence,saved:true,width:480,height:706,surface:'tablet'});
    timers[0]();assert.equal(output.at(-1).kind,'frameReady');helper.receive({action:'frameAck',revision:2,frameSequence:next.sequence});timers[0]();
    const warm=qml.at(-1);now+=8001;timers[0]();timers[0]();assert.match(output.findLast(value=>value.kind==='error').message,/8 seconds/);
    helper.receive({action:'home',revision:2});timers[0]();assert.equal(qml.filter(value=>value.kind==='capture').length,3,'Retry waits for the still-outstanding GPU callback');
    fromQml.emit({kind:'frame',revision:2,sequence:warm.sequence,saved:false,cancelled:true});timers[0]();assert.equal(qml.filter(value=>value.kind==='capture').length,4,'Retry resumes once cancelled grab resolves');helper.close();
});
test('Qt callback records reach the socket only on the script queue and are suppressed after authority change or close',async()=>{
    const queued=[],timers=[],qml=[],output=[];const fromQml=signal(),screenChanged=signal();
    const context=vm.createContext({Tablet:{getTablet:()=>({screenChanged,loadQMLSource:()=>{}})},OverlayWindow:function(){this.fromQml=fromQml;this.sendToQml=value=>qml.push(value);this.close=()=>{};},Audio:{muted:true},Script:{load:()=>{},setTimeout:(fn,delay)=>{if(delay===0)queued.push(fn);},setInterval:fn=>timers.push(fn),clearInterval:()=>{}},Date});
    vm.runInContext(await readFile(new URL('./native-tablet.js',import.meta.url),'utf8'),context);
    const helper=context.createBrowserTablet({qmlURL:'file:///capture.qml',framePath:'/private/frame',defaultScriptsURL:'file:///defaultScripts.js',send:value=>output.push(JSON.parse(JSON.stringify(value)))});
    const flush=()=>timers[0]();
    helper.setAuthority(1,true);helper.receive({action:'open',revision:1});flush();const capture=qml.at(-1);
    const rect={x:0,y:0,width:480,height:706,toJSON:()=>{throw Error('Qt wrapper must not reach JSON');}};
    fromQml.emit({kind:'frame',revision:1,sequence:capture.sequence,saved:true,width:480,height:706,surface:'tablet',tabletRect:rect});
    assert.equal(output.filter(value=>value.kind==='frameReady').length,0,'UI callback never writes directly to engine-owned socket');
    flush();assert.deepEqual(output.at(-1).tabletRect,{x:0,y:0,width:480,height:706});
    helper.receive({action:'frameAck',revision:1,frameSequence:capture.sequence});timers[0]();const next=qml.at(-1);
    fromQml.emit({kind:'frame',revision:1,sequence:next.sequence,saved:true,width:480,height:706,surface:'tablet'});helper.setAuthority(2,false);flush();
    assert.equal(output.filter(value=>value.kind==='frameReady').length,1,'Queued former-domain pixels cannot survive revocation');
    helper.setAuthority(3,true);helper.receive({action:'open',revision:3});helper.close();const count=output.length;flush();assert.equal(output.length,count,'Closed session cannot send queued UI messages');
});
