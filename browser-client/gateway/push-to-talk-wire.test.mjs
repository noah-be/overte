// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {readFile} from 'node:fs/promises';import {randomUUID,randomBytes} from 'node:crypto';
import {SharedTeardown} from './process-lifecycle.mjs';import {PushToTalkSession} from './push-to-talk.mjs';
import {NativeHeartbeat} from './socket-heartbeat.mjs';
import {AvatarSnapshotSender} from './avatar-snapshot-sender.mjs';
const source=await readFile(new URL('./server.mjs',import.meta.url),'utf8');
function harness(){
    const browserHandlers={},nativeHandlers={},writes=[],sent=[],sessions=new Map(),sockets=new Set();
    const browser={readyState:1,on(name,fn){browserHandlers[name]=fn;}},native={readyState:1,on(name,fn){nativeHandlers[name]=fn;},close(){throw Error('Unexpected native protocol refusal');}};
    const send=(target,value)=>sent.push({target,value});
    const start=source.indexOf('class Session extends SharedTeardown {'),end=source.indexOf('\nconst server = http.createServer',start);
    const ActualSession=vm.runInNewContext(source.slice(start,end)+'\nSession;',{SharedTeardown,PushToTalkSession,randomBytes,randomUUID,send,sessions,WebSocket:{OPEN:1},setTimeout:()=>1,clearTimeout(){}});
    let session;
    class Session extends ActualSession{
        async launch(){session=this;this.connected=true;this.permissionsApproved=true;this.permissionRevision=1;this.muted=false;
            // External native admission/playback are controlled; the constructor,
            // browser/native handlers and PCM/command gates are actual source.
            this.playback={stdin:{writableLength:0,write(data){writes.push(Buffer.from(data));}}};}
    }
    const begin=source.indexOf("browserServer.on('connection'"),finish=source.indexOf("nativeServer.on('connection'",begin);
    vm.runInNewContext(source.slice(begin,finish),{process:{env:{}}, AvatarSnapshotSender,Session,sessions,sockets,maximumSessions:1,shuttingDown:false,send,WebSocket:{OPEN:1},cookie:()=> 'owned-test-cookie',equal:(a,b)=>a===b,
        browserServer:{on(name,fn){fn(browser,{headers:{}});}}});
    vm.runInNewContext(source.slice(source.indexOf('function avatarFlowEnabled('),source.indexOf('function avatarFlowDistance('))+source.slice(finish,source.indexOf('const heartbeat =',finish)),{process:{env:{}},
        sessions,sockets,send,NativeHeartbeat,equal:(a,b)=>a===b,setTimeout:()=>1,clearTimeout(){},
        nativeServer:{on(name,fn){fn(native);}}});
    const dispatch=(value,binary=false)=>browserHandlers.message(binary?value:Buffer.from(JSON.stringify(value)),binary);
    const receive=value=>nativeHandlers.message(Buffer.from(JSON.stringify(value)));
    return {dispatch,receive,writes,sent,get session(){return session;},async join(){await dispatch({type:'join'});await receive({type:'nativeHello',token:session.token});sent.length=0;}};
}
test('actual production handlers gate PCM until effective native hold and close PCM synchronously on release',async()=>{
    const f=harness();await f.join();const pcm=Buffer.alloc(1920,1);
    await f.dispatch(pcm,true);assert.equal(f.writes.length,0);
    await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:0,enabled:true,held:false,muted:true});
    await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});await f.dispatch(pcm,true);assert.equal(f.writes.length,0);
    await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:1,enabled:true,held:true,muted:false});await f.dispatch(pcm,true);assert.equal(f.writes.length,1);
    await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:false});await f.dispatch(pcm,true);assert.equal(f.writes.length,1);
    await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:1,enabled:true,held:true,muted:false});await f.dispatch(pcm,true);assert.equal(f.writes.length,1);
});
test('actual original PCM size, writable backlog, mute and approval gates survive ordinary mode',async()=>{
    const f=harness();await f.join();await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:0,enabled:false,held:false,muted:false});
    await f.dispatch(Buffer.alloc(1920),true);assert.equal(f.writes.length,1);
    await f.dispatch(Buffer.alloc(19201),true);await f.dispatch(Buffer.alloc(19202),true);assert.equal(f.writes.length,1);
    f.session.playback.stdin.writableLength=19200;await f.dispatch(Buffer.alloc(1920),true);assert.equal(f.writes.length,1);
    f.session.playback.stdin.writableLength=0;await f.dispatch({type:'mute',muted:true});await f.dispatch(Buffer.alloc(1920),true);assert.equal(f.writes.length,1);
    f.session.muted=false;f.session.permissionsApproved=false;await f.dispatch(Buffer.alloc(1920),true);assert.equal(f.writes.length,1);
});
test('actual native handler discards stale revision and unknown envelope data; no command before approved native PTT state',async()=>{
    const f=harness();await f.join();await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});assert.equal(f.sent.length,0);
    await f.receive({type:'pushToTalkState',version:1,permissionRevision:2,sequence:0,enabled:true,held:false,muted:true});assert.equal(f.sent.length,0);
    await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:0,enabled:true,held:false,muted:true,secret:'PRIVATE'});
    assert.equal(f.sent.length,1);assert.equal(Object.hasOwn(f.sent[0].value,'secret'),false);
    await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});assert.equal(f.sent.at(-1).value.held,true);
    f.session.permissionsApproved=false;await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:1,enabled:true,held:true,muted:false});assert.equal(f.sent.length,2);
});

for (const firstMuted of [true, false]) test(`actual explicit mute ${firstMuted} cancels a held ACK; only a fresh command and native ACK reopen PCM`,async()=>{
 const f=harness();await f.join();const pcm=Buffer.alloc(1920,1);
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:0,enabled:true,held:false,muted:true});
 await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:1,enabled:true,held:true,muted:false});
 await f.dispatch(pcm,true);assert.equal(f.writes.length,1,'Effective initial held ACK admits PCM');
 await f.dispatch({type:'mute',muted:firstMuted});
 await f.dispatch({type:'mute',muted:false});
 await f.dispatch(pcm,true);assert.equal(f.writes.length,1,'Ordinary mute/rearm must not reuse a held ACK');
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:1,enabled:true,held:true,muted:false});
 await f.dispatch(pcm,true);assert.equal(f.writes.length,1,'A delayed duplicate ACK cannot rearm cancelled intent');
 await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:2,held:true});
 await f.dispatch(pcm,true);assert.equal(f.writes.length,1,'A fresh held command still requires its matching ACK');
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:2,enabled:true,held:true,muted:false});
 await f.dispatch(pcm,true);assert.equal(f.writes.length,2,'Fresh monotonic hold plus effective native ACK admits PCM');
});
test('actual ordinary-mode quick mute/rearm preserves coalesced state; invalid mute does not cancel a hold',async()=>{
 const f=harness();await f.join();const pcm=Buffer.alloc(1920);
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:0,enabled:false,held:false,muted:false});
 await f.dispatch(pcm,true);assert.equal(f.writes.length,1);
 await f.dispatch({type:'mute',muted:true});await f.dispatch(pcm,true);assert.equal(f.writes.length,1);
 await f.dispatch({type:'mute',muted:false});await f.dispatch(pcm,true);assert.equal(f.writes.length,2,'Unchanged normal-mode state need not be republished');
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:0,enabled:true,held:false,muted:true});
 await f.dispatch({type:'pushToTalk',version:1,permissionRevision:1,sequence:1,held:true});
 await f.receive({type:'pushToTalkState',version:1,permissionRevision:1,sequence:1,enabled:true,held:true,muted:false});
 await f.dispatch({type:'mute',muted:'true'});await f.dispatch(pcm,true);assert.equal(f.writes.length,3,'Only a validated Boolean mute command is a consent boundary');
});
