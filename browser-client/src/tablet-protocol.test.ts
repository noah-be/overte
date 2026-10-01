// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTabletMessage} from './tablet-protocol';
import {BrowserTablet} from './tablet';
import {DEFAULT_BROWSER_GRAPHICS} from '../shared/browser-graphics.mjs';
test('tablet response validates native authority and browser image geometry',()=>{
    assert.equal(parseTabletMessage({type:'tablet',kind:'state',revision:1,visible:true,loading:false,screen:'Home'}).kind,'state');
    const frame={type:'tablet',kind:'frame',revision:1,sequence:2,width:480,height:706,mime:'image/png',data:'AQID',surface:'tablet'};
    assert.equal(parseTabletMessage(frame).kind,'frame');
    for(const patch of [{revision:0},{sequence:-1},{width:4096},{height:NaN},{data:'data:image/png;base64,AQID'},{surface:'world'},{mime:'image/jpeg'}])assert.throws(()=>parseTabletMessage({...frame,...patch}));
});

test('native chat data is bounded and never interpreted as browser markup',()=>{
    const message={type:'tablet',kind:'chat',revision:2,sequence:3,channel:'domain',text:'<script>window.owned=true</script> 👋',displayName:'Native',senderId:'12345678-1234-1234-1234-123456789abc'};
    assert.equal(parseTabletMessage(message).kind,'chat');
    for(const patch of [{sequence:0},{channel:'private'},{text:'👋'.repeat(2049)},{senderId:'invalid'}])assert.throws(()=>parseTabletMessage({...message,...patch}));
});

test('graphics requests retain native authority and sanitize unsupported transport properties',()=>{
    const message={type:'tablet',kind:'graphics',revision:3,schemaVersion:1,requestId:2,operation:'change',field:'resolutionPercent',value:50};
    assert.deepEqual(parseTabletMessage({...message,privateWorkerRatio:.1}),message);
    for(const patch of [{revision:0},{schemaVersion:2},{requestId:0},{field:'nativeWorkerViewport'},{value:NaN},{value:25}])
        assert.throws(()=>parseTabletMessage({...message,...patch}));
});

test('actual Tablet bridge uses its ordinary sequenced reply and rejects disconnected or stale graphics work',()=>{
    const sent:Record<string,unknown>[]=[];let invoked=0;
    const tablet=Object.create(BrowserTablet.prototype);
    Object.assign(tablet,{connected:true,disposed:false,revision:3,sequence:12,options:{
        send:(message:Record<string,unknown>)=>sent.push(message),onStatus:()=>{},
        onGraphics:()=>{invoked++;return{schemaVersion:1,requestId:2,accepted:true,settings:{...DEFAULT_BROWSER_GRAPHICS,resolutionPercent:50}};},
    }});
    const request={type:'tablet' as const,kind:'graphics' as const,revision:3,schemaVersion:1 as const,requestId:2,operation:'request' as const};
    tablet.receive(request);
    assert.equal(invoked,1);assert.equal(sent.length,1);
    assert.deepEqual(sent[0],{type:'tablet',action:'graphicsResult',revision:3,sequence:13,schemaVersion:1,requestId:2,accepted:true,settings:{...DEFAULT_BROWSER_GRAPHICS,resolutionPercent:50}});
    tablet.receive({...request,revision:2});assert.equal(invoked,1);
    tablet.connected=false;tablet.receive(request);assert.equal(invoked,1);
});

test('Tablet graphics callback cannot reply after synchronous authority revocation',()=>{
    const tablet=Object.create(BrowserTablet.prototype);let sent=0;
    Object.assign(tablet,{connected:true,disposed:false,revision:3,sequence:0,options:{send:()=>sent++,onStatus:()=>{},onGraphics:()=>{
        tablet.connected=false;return{schemaVersion:1,requestId:1,accepted:true,settings:DEFAULT_BROWSER_GRAPHICS};
    }}});
    tablet.receive({type:'tablet',kind:'graphics',revision:3,schemaVersion:1,requestId:1,operation:'request'});
    assert.equal(sent,0);
});
