// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTabletMessage} from './tablet-protocol';
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
