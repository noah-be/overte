// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {randomUUID} from 'node:crypto';
import vm from 'node:vm';
import WebSocket,{WebSocketServer} from 'ws';
import {SharedTeardown} from './process-lifecycle.mjs';
import {AvatarSnapshotSender} from './avatar-snapshot-sender.mjs';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function until(predicate){for(let i=0;i<100;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,5));}assert.fail('Production admission did not reach the expected state');}

// Real WebSocket messages exercise the actual production handler; only external
// native worker creation and process teardown are controllably deferred.
async function harness(t){
    const source=await readFile(new URL('./server.mjs',import.meta.url),'utf8');
    const start=source.indexOf("browserServer.on('connection'"),end=source.indexOf("nativeServer.on('connection'",start);
    assert(start>=0&&end>start);
    const server=createServer(),browserServer=new WebSocketServer({server});
    const sessions=new Map(),sockets=new Set(),created=[],clients=[];
    let highWater=0;
    class Session extends SharedTeardown{
        constructor(browser,owner,isCurrent){super();this.id=randomUUID();this.browser=browser;this.owner=owner;this.isCurrent=isCurrent;this.closed=false;this.closeCalls=0;this.native={readyState:WebSocket.OPEN};this.cleanup=new Promise(resolve=>{this.release=resolve;});created.push(this);}
        async launch(){highWater=Math.max(highWater,sessions.size);this.browser.send(JSON.stringify({type:'fixtureAllocated',index:created.indexOf(this)}));}
        close(...args){this.closeCalls++;return super.close(...args);}
        revoke(){this.closed=true;}
        async teardown(notify=true){await this.cleanup;sessions.delete(this.id);if(this.finalCleanup)await this.finalCleanup;if(notify&&this.isCurrent()&&this.browser.readyState===WebSocket.OPEN)this.browser.send(JSON.stringify({type:'state',state:'disconnected'}));}
    }
    const context=vm.createContext({AvatarSnapshotSender,Session,sessions,sockets,maximumSessions:1,shuttingDown:false,browserServer,WebSocket,
        cookie:request=>request.headers.cookie, equal:(a,b)=>a===b,send:(browser,value)=>{if(browser.readyState===WebSocket.OPEN)browser.send(JSON.stringify(value));},pose:()=>{}});
    vm.runInContext(source.slice(start,end),context);
    server.listen(0,'127.0.0.1');await once(server,'listening');
    const connect=async(owner='visitor-a')=>{const socket=new WebSocket(`ws://127.0.0.1:${server.address().port}`,{headers:{cookie:owner}});socket.messages=[];socket.on('message',data=>socket.messages.push(JSON.parse(data.toString())));await once(socket,'open');clients.push(socket);return socket;};
    const send=(socket,type)=>socket.send(JSON.stringify({type,domain:'overte://127.0.0.2:45102'}));
    t.after(async()=>{for(const socket of clients)socket.terminate();for(const session of created){session.release();session.close(false);}await Promise.all(created.map(session=>session.closePromise));for(const socket of sockets)socket.terminate();await new Promise(resolve=>browserServer.close(resolve));await new Promise(resolve=>server.close(resolve));});
    return {connect,send,created,sessions,context,get highWater(){return highWater;}};
}

test('same-owner rapid rejoin waits for actual cleanup without exceeding the worker cap',async t=>{
    const state=await harness(t),socket=await state.connect();state.send(socket,'join');await until(()=>state.created.length===1);
    state.send(socket,'leave');await until(()=>state.created[0].closed);state.send(socket,'join');await until(()=>state.created[0].closeCalls>=2);
    assert.equal(state.created.length,1,'No replacement worker before owned teardown completes');assert.equal(state.sessions.size,1);
    state.created[0].release();await until(()=>state.created.length===2);assert.equal(state.highWater,1);assert.equal(state.sessions.size,1);
    assert.equal(socket.messages.some(message=>message.state==='error'),false);
});
test('foreign active and foreign closing sessions reject immediately without waiting or allocation',async t=>{
    const state=await harness(t),owner=await state.connect(),foreign=await state.connect('visitor-b');state.send(owner,'join');await until(()=>state.created.length===1);
    state.send(foreign,'join');await until(()=>foreign.messages.some(message=>message.state==='error'));assert.equal(state.created.length,1);
    state.send(owner,'leave');await until(()=>state.created[0].closed);const count=foreign.messages.length;state.send(foreign,'join');await until(()=>foreign.messages.length>count);assert.equal(state.created.length,1);assert.equal(foreign.messages.at(-1).state,'error');
});
for(const cancellation of ['leave','socket-close','shutdown'])test(`${cancellation} cancels an owned cleanup wait and prevents late allocation`,async t=>{
    const state=await harness(t),socket=await state.connect();state.send(socket,'join');await until(()=>state.created.length===1);
    state.send(socket,'leave');await until(()=>state.created[0].closed);state.send(socket,'join');await until(()=>state.created[0].closeCalls>=2);
    if(cancellation==='leave')state.send(socket,'leave');else if(cancellation==='socket-close'){socket.close();await once(socket,'close');}else state.context.shuttingDown=true;
    await tick();state.created[0].release();await until(()=>state.sessions.size===0);await tick();await tick();assert.equal(state.created.length,1,'Cancelled wait cannot allocate a native worker');assert.equal(state.highWater,1);
});
test('second pending join is rejected while the first owned cleanup wait remains valid',async t=>{
    const state=await harness(t),socket=await state.connect();state.send(socket,'join');await until(()=>state.created.length===1);state.send(socket,'leave');await until(()=>state.created[0].closed);
    state.send(socket,'join');state.send(socket,'join');await until(()=>socket.messages.some(message=>message.state==='error'));assert.equal(state.created.length,1);
    state.created[0].release();await until(()=>state.created.length===2);assert.equal(state.highWater,1,'An overlapping join cannot consume another worker slot');
});

test('capacity is rechecked when another owner fills the slot before final cleanup resolves',async t=>{
    const state=await harness(t),owner=await state.connect(),foreign=await state.connect('visitor-b');state.send(owner,'join');await until(()=>state.created.length===1);
    let finish;state.created[0].finalCleanup=new Promise(resolve=>{finish=resolve;});t.after(()=>finish());
    state.send(owner,'leave');await until(()=>state.created[0].closed);state.send(owner,'join');await until(()=>state.created[0].closeCalls>=2);
    state.created[0].release();await until(()=>state.sessions.size===0);state.send(foreign,'join');await until(()=>state.created.length===2);
    finish();await until(()=>owner.messages.some(message=>message.state==='error'));assert.equal(state.created.length,2);assert.equal(state.sessions.size,1);assert.equal(state.highWater,1);
});
