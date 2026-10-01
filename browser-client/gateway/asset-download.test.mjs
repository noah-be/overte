// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { downloadAsset } from './asset-download.mjs';
import { SessionAssets } from './session-assets.mjs';

async function origin(handler) {
    const server = http.createServer(handler); server.listen(0, '127.0.0.1'); await once(server, 'listening');
    return { url: `http://127.0.0.1:${server.address().port}`, close: () => {
        server.closeAllConnections(); return new Promise(resolve => server.close(resolve));
    } };
}
const waitUntil = async predicate => {
    const deadline = Date.now() + 3000;
    while (!predicate()) { if (Date.now() > deadline) throw Error('HTTP lifecycle did not complete within three seconds.'); await new Promise(resolve => setTimeout(resolve, 10)); }
};

test('real HTTP duplicate requests download once and reuse visitor bytes without a browser cache', async () => {
    let requests = 0;
    const server = await origin((request, response) => {
        requests++; response.writeHead(200, { 'content-type': 'image/png' });
        setTimeout(() => response.end(Buffer.from([137,80,78,71])), 20);
    });
    const origins = new Set([server.url]);
    const assets = new SessionAssets({ authority: () => 'guest|1', load: (url, signal) => downloadAsset(url, origins, signal) });
    try {
        const [a,b] = await Promise.all([assets.request(server.url+'/texture'), assets.request(server.url+'/texture')]);
        assert.equal(requests, 1); assert.equal(a.type, 'image/png'); assert.deepEqual(a.data,b.data);
        await assets.request(server.url+'/texture'); assert.equal(requests,1);
    } finally { assets.close(); await server.close(); }
});
test('last shared HTTP reader cancellation closes its actual upstream body and permits retry', async () => {
    let requests = 0, closed = 0;
    const server = await origin((request, response) => {
        requests++; response.writeHead(200); response.write('header');
        response.on('close', () => closed++);
    });
    const assets = new SessionAssets({ authority: () => 'guest|1', load: (url, signal) => downloadAsset(url, new Set([server.url]), signal) });
    try {
        const a = new AbortController(), b = new AbortController();
        const first = assets.request(server.url+'/stream', a.signal), second = assets.request(server.url+'/stream', b.signal);
        const firstRejection = assert.rejects(first,/cancelled/), secondRejection = assert.rejects(second,/cancelled/);
        await waitUntil(() => requests===1); a.abort(); await firstRejection;
        assert.equal(closed,0,'Another real reader still owns the upstream body');
        b.abort(); await secondRejection; await waitUntil(() => closed===1 && assets.active===0);
        const c = new AbortController(); const retry = assets.request(server.url+'/stream', c.signal); const rejected = assert.rejects(retry,/cancelled/);
        await waitUntil(() => requests===2); c.abort(); await rejected; await waitUntil(() => closed===2);
    } finally { assets.close(); await server.close(); }
});
test('real HTTP queue drains under the original sixteen active-download bound', async () => {
    let active = 0, maximum = 0, requests = 0;
    const server = await origin((request,response) => {
        requests++; maximum=Math.max(maximum,++active);
        setTimeout(() => { active--; response.end(request.url); },25);
    });
    const assets = new SessionAssets({ authority: () => 'guest|1', load: (url, signal) => downloadAsset(url,new Set([server.url]),signal) });
    try {
        const results=await Promise.all(Array.from({length:32},(_,index)=>assets.request(server.url+'/'+index)));
        assert.equal(results.length,32);assert.equal(requests,32);assert.ok(maximum<=16);
        assert.ok(maximum>1,'Downloads genuinely overlap rather than becoming serial');
    } finally {assets.close();await server.close();}
});
test('every real HTTP redirect is freshly allowlisted and credentials are never forwarded', async () => {
    let foreignRequests=0, trustedRequests=0;
    const foreign=await origin((request,response)=>{foreignRequests++;response.end('private');});
    const trusted=await origin((request,response)=>{trustedRequests++;response.writeHead(302,{location:foreign.url+'/private'});response.end();});
    try {
        await assert.rejects(downloadAsset(trusted.url+'/redirect',new Set([trusted.url]),new AbortController().signal),/not enabled/);
        assert.equal(trustedRequests,1);assert.equal(foreignRequests,0);
        await assert.rejects(downloadAsset(trusted.url.replace('http://','http://user:password@')+'/secret',new Set([trusted.url]),new AbortController().signal),/not enabled/);
        assert.equal(trustedRequests,1);
    } finally {await trusted.close();await foreign.close();}
});
test('oversized advertised and streamed HTTP assets are aborted without cache retention', async () => {
    const server=await origin((request,response)=>{
        if(request.url==='/declared'){response.writeHead(200,{'content-length':32*1024*1024+1});response.end();return;}
        response.writeHead(200);response.end(Buffer.alloc(32*1024*1024+1));
    });
    const assets=new SessionAssets({authority:()=> 'guest|1',load:(url,signal)=>downloadAsset(url,new Set([server.url]),signal)});
    try {
        for(const name of ['declared','streamed'])await assert.rejects(assets.request(server.url+'/'+name),/32 MiB/);
        assert.equal(assets.bytes,0);assert.equal(assets.entries.size,0);assert.equal(assets.active,0);
    } finally {assets.close();await server.close();}
});
