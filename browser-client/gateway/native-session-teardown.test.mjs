// SPDX-License-Identifier: Apache-2.0
// Execute actual production lifecycle bodies without importing the live server.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {SharedTeardown} from './process-lifecycle.mjs';

const source=await readFile(new URL('./server.mjs',import.meta.url),'utf8');
function section(start,end){
    assert.equal(source.split(start).length,2);
    const begin=source.indexOf(start),finish=source.indexOf(end,begin);
    assert(finish>begin);return source.slice(begin,finish).trim();
}
const teardown=section('    async teardown(notify = true) {','\n}\n\nconst server');
const revoke=section('    revoke() {','    async teardown(notify = true) {');
const shutdown=section('function shutdown() {','\nfor (const signal');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function fixture(body=teardown){
    const sessions=new Map(),events=[],removing=deferred(),entered=deferred();
    let removalCalls=0;
    const rm=async()=>{removalCalls++;events.push('remove-start');entered.resolve();await removing.promise;events.push('remove-end');};
    const terminate=async child=>{events.push('retire-'+child.role);if(child.wait)await child.wait;};
    const send=()=>events.push('notify');
    const actual=new Function('sessions','rm','terminateProcess','WebSocket','send','return ({'+revoke+',\n'+body+'});')(sessions,rm,terminate,{OPEN:1},send);
    class Session extends SharedTeardown {isCurrent(){return true;}}
    Session.prototype.revoke=actual.revoke;Session.prototype.teardown=actual.teardown;
    const item=new Session(),http=new AbortController();
    Object.assign(item,{id:'owned-fixture-session',permissionsApproved:true,connected:true,muted:false,
        pushToTalk:{reset:()=>events.push('ptt-reset')},assets:{close:()=>events.push('assets-close')},
        protocolInspection:new AbortController(),workerAbort:new AbortController(),tablet:{close:()=>events.push('tablet-close')},
        httpAssets:new Set([http]),pendingAssets:new Map(),processes:[],directory:'owned-fixture-directory'});
    sessions.set(item.id,item);
    const stop=new Function('sessions','sockets','server','process','clearInterval','heartbeat','policyWatchdog','publicPlaceWatchdog',
        'let shutdownPromise,shuttingDown=false;'+shutdown+';return shutdown;')(sessions,[],
        {close:callback=>{events.push('server-close');callback();}},
        {exit:()=>events.push('process-exit')},()=>{},0,0,0);
    return {item,sessions,events,removing,entered,http,stop,get removalCalls(){return removalCalls;}};
}
async function microtasks(){for(let i=0;i<5;i++)await Promise.resolve();}

test('gateway shutdown awaits the exact already-closing session until owned files retire',async()=>{
    const f=fixture(),leaving=f.item.close(false);
    assert.equal(f.item.permissionsApproved,false);assert.equal(f.item.connected,false);assert.equal(f.item.muted,true);
    assert.equal(f.item.protocolInspection.signal.aborted,true);assert.equal(f.item.workerAbort.signal.aborted,true);
    await f.entered.promise;assert.equal(f.http.signal.aborted,true);assert.equal(f.sessions.get(f.item.id),f.item);
    const stopping=f.stop();await microtasks();assert.equal(f.events.includes('process-exit'),false);
    assert.equal(f.item.close(true),leaving);assert.equal(f.removalCalls,1);
    f.removing.resolve();await leaving;await stopping;
    assert.equal(f.sessions.size,0);assert(f.events.indexOf('remove-end')<f.events.indexOf('process-exit'));
    assert.equal(f.events.includes('notify'),false);assert.equal(f.events.filter(x=>x==='ptt-reset').length,1);
});

test('historical premature untracking exits while the same owned removal is pending',async()=>{
    const current='if (this.directory) await rm(this.directory, { recursive: true, force: true }).catch(() => {});\n        sessions.delete(this.id);';
    const old='sessions.delete(this.id);\n        if (this.directory) await rm(this.directory, { recursive: true, force: true }).catch(() => {});';
    assert.equal(teardown.split(current).length,2);
    const f=fixture(teardown.replace(current,old)),leaving=f.item.close(false);await f.entered.promise;
    const stopping=f.stop();await microtasks();assert.equal(f.sessions.size,0);assert.equal(f.events.includes('process-exit'),true);
    f.removing.resolve();await leaving;await stopping;
});

test('native audio and other children retire before directory removal or slot release',async()=>{
    const f=fixture(),native=deferred();f.item.nativeProcess={role:'native',wait:native.promise};
    f.item.audioServer={role:'audio'};f.item.processes=[f.item.nativeProcess,{role:'other'},f.item.audioServer];
    f.item.files={close:()=>{f.events.push('files-close');}};f.item.network={release:()=>f.events.push('network-release')};
    f.item.worker={release:()=>f.events.push('worker-release')};
    const leaving=f.item.close(false);await microtasks();assert.equal(f.events.includes('retire-native'),true);
    assert.equal(f.events.includes('retire-audio'),false);assert.equal(f.removalCalls,0);assert.equal(f.sessions.size,1);
    native.resolve();await f.entered.promise;
    for(const event of ['retire-native','retire-other','retire-audio','network-release','worker-release'])assert(f.events.indexOf(event)<f.events.indexOf('remove-start'));
    assert(f.events.indexOf('retire-native')<f.events.indexOf('retire-audio'));
    f.removing.resolve();await leaving;assert.equal(f.sessions.size,0);
});

test('original recursive-removal error semantics and initiating notification remain unchanged',async()=>{
    const f=fixture(),leaving=f.item.close(true);await f.entered.promise;
    assert.equal(f.item.close(false),leaving);assert.equal(f.sessions.size,1);
    f.removing.reject(new Error('fixed-owned-removal-error'));await leaving;
    assert.equal(f.sessions.size,0);assert.equal(f.events.filter(x=>x==='notify').length,1);
    assert.equal(f.removalCalls,1);assert.equal(f.item.close(),leaving);
});

test('concurrent gateway shutdown callers share completion while removal stays owned',async()=>{
    const f=fixture(),first=f.stop();await f.entered.promise;
    assert.equal(f.stop(),first);assert.equal(f.removalCalls,1);assert.equal(f.sessions.size,1);
    await microtasks();assert.equal(f.events.includes('server-close'),false);
    f.removing.resolve();await first;
    assert.equal(f.events.filter(x=>x==='server-close').length,1);assert.equal(f.events.filter(x=>x==='process-exit').length,1);
});
