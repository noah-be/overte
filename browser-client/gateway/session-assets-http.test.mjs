// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomBytes, randomUUID } from 'node:crypto';
import { EventEmitter } from 'node:events';
import vm from 'node:vm';
import { SessionAssets } from './session-assets.mjs';
import { PushToTalkSession } from './push-to-talk.mjs';
import { SharedTeardown } from './process-lifecycle.mjs';
import { approvedAssetAddress, ASSET_SANDBOX_POLICY } from './validation.mjs';

async function fixture(load) {
    const source = await readFile(new URL('./server.mjs',import.meta.url),'utf8');
    const classStart=source.indexOf('class Session extends SharedTeardown {');
    const classEnd=source.indexOf('\nconst server = http.createServer',classStart);
    const serverStart=source.indexOf('const server = http.createServer');
    const serverEnd=source.indexOf('// Allowed clipboard quotation',serverStart);
    assert.ok(classStart>=0&&classEnd>classStart&&serverStart===classEnd+1&&serverEnd>serverStart);
    const sessions=new Map(), origins=new Set(['https://assets.example']);
    const context={SharedTeardown,randomBytes,randomUUID,SessionAssets,PushToTalkSession,approvedAssetAddress,downloadAsset:(url,origins,signal)=>load(url,signal),
        assetOrigins:origins,publicAssetOrigins:new Set(),Buffer};
    const GatewaySession=vm.runInNewContext(source.slice(classStart,classEnd)+'\nSession;',context);
    const session=new GatewaySession({},'visitor-cookie');session.permissionsApproved=true;session.permissionRevision=1;
    session.nativeDomain='overte://test:40102';sessions.set(session.id,session);
    let handler;
    const json=(response,code,value)=>{response.writeHead(code,{'content-type':'application/json'});response.end(JSON.stringify(value));};
    vm.runInNewContext(source.slice(serverStart,serverEnd),{
        shuttingDown:false,URL,port:8090,sessions,cookie:request=>request.headers.cookie,equal:(a,b)=>a===b,
        json,AbortController,ASSET_SANDBOX_POLICY,http:{createServer(callback){handler=callback;return{};}},
    });
    return {session,async request(asset='https://assets.example/texture',owner='visitor-cookie',during){
        const request={url:`/api/assets/${session.id}?url=${encodeURIComponent(asset)}`,headers:{cookie:owner}};
        const response=new EventEmitter();response.destroyed=false;response.writableEnded=false;
        response.writeHead=(code,headers)=>{response.status=code;response.headers=headers;};
        response.end=data=>{response.body=data;response.writableEnded=true;};
        const operation=handler(request,response);during?.(response);await operation;return response;
    }};
}
test('actual HTTP asset handler rechecks owner, rights and origin for byte cache hits with inert response headers',async()=>{
    let loads=0;const f=await fixture(async()=>{loads++;return{data:Buffer.from('<script>secret()</script>'),type:'text/html'};});
    const first=await f.request(),cached=await f.request();assert.equal(loads,1);assert.equal(cached.status,200);
    assert.equal(cached.headers['cache-control'],'private, no-store');
    assert.equal(first.headers['x-overte-asset-source'],'download'); assert.equal(cached.headers['x-overte-asset-source'],'memory');
    assert.equal(cached.headers['content-length'],cached.body.length);assert.equal(cached.headers['content-security-policy'],ASSET_SANDBOX_POLICY);
    assert.equal(cached.headers['x-content-type-options'],'nosniff');assert.deepEqual(first.body,cached.body);
    assert.equal((await f.request(undefined,'foreign-cookie')).status,403);
    assert.equal((await f.request('https://unapproved.example/texture')).status,502);
    f.session.permissionsApproved=false;assert.equal((await f.request()).status,403);assert.equal(loads,1);
    f.session.assets.close();
});
test('actual HTTP handler never releases bytes completed under an obsolete permission revision',async()=>{
    let finish;const f=await fixture(()=>new Promise(resolve=>{finish=resolve;}));
    const pending=f.request();await new Promise(resolve=>setImmediate(resolve));f.session.permissionRevision=2;
    finish({data:Buffer.from('OLD-PRIVATE-BYTES'),type:'image/png'});
    const response=await pending;assert.ok(response.status>=400);assert.doesNotMatch(String(response.body),/OLD-PRIVATE-BYTES/);
    assert.equal(f.session.assets.entries.size,0);f.session.assets.close();
});
test('actual HTTP response close cancels its only loader without caching late bytes',async()=>{
    let cancellation,finish;const f=await fixture((url,signal)=>{cancellation=signal;return new Promise(resolve=>{finish=resolve;});});
    const pending=f.request(undefined,undefined,response=>setImmediate(()=>{response.destroyed=true;response.emit('close');}));
    await new Promise(resolve=>setImmediate(resolve));assert.equal(cancellation.aborted,true);
    finish({data:Buffer.from('LATE-BYTES'),type:'image/png'});await pending;
    assert.equal(f.session.assets.entries.size,0);f.session.assets.close();
});
test('actual shared HTTP responses label each reader without global-counter races',async()=>{
    let finish,loads=0;const f=await fixture(()=>{loads++;return new Promise(resolve=>{finish=resolve;});});
    const first=f.request(),second=f.request();await new Promise(resolve=>setImmediate(resolve));assert.equal(loads,1);
    finish({data:Buffer.from('shared PNG bytes'),type:'image/png'});
    const [a,b]=await Promise.all([first,second]);assert.equal(a.status,200);assert.equal(b.status,200);
    assert.equal(a.headers['x-overte-asset-source'],'download');assert.equal(b.headers['x-overte-asset-source'],'shared');
    assert.equal(a.headers['content-length'],a.body.length);assert.equal(b.headers['content-length'],b.body.length);
    assert.deepEqual(a.body,b.body);f.session.assets.close();
});
test('actual session byte keys deduplicate HTTP fragments while preserving resource query variants',async()=>{
    const loaded=[];const f=await fixture(async address=>{loaded.push(address);return{data:Buffer.from(address),type:'application/octet-stream'};});
    const first=await f.request('https://assets.example/mesh.fbx?version=1#material:one');
    const second=await f.request('https://assets.example/mesh.fbx?version=1#material:two');
    assert.deepEqual(loaded,['https://assets.example/mesh.fbx?version=1']);
    assert.equal(first.headers['x-overte-asset-source'],'download');assert.equal(second.headers['x-overte-asset-source'],'memory');
    assert.deepEqual(first.body,second.body);
    await f.request('https://assets.example/mesh.fbx?version=2#material:one');
    assert.deepEqual(loaded,['https://assets.example/mesh.fbx?version=1','https://assets.example/mesh.fbx?version=2']);
    f.session.assets.close();
});
