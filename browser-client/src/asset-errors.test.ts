// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {requireAssetResponse} from './asset-errors';
test('real gateway rejection details remain readable and successful binary bytes remain untouched',async()=>{
    const valid = new Response(new Uint8Array([0,128,255]));
    await requireAssetResponse(valid,'FBX');
    assert.deepEqual(new Uint8Array(await valid.arrayBuffer()),new Uint8Array([0,128,255]));
    await assert.rejects(requireAssetResponse(new Response(JSON.stringify({error:'The asset origin is not enabled by the gateway administrator.'}),{
        status:502,headers:{'Content-Type':'application/json'},
    }),'Selected avatar FST'),/Selected avatar FST request returned HTTP 502: The asset origin is not enabled/);
    await assert.rejects(requireAssetResponse(new Response('<html>external error</html>',{status:404}),'FBX'),/^Error: FBX request returned HTTP 404\.$/);
});
test('gateway error bodies are bounded and invalid data cannot obscure the asset HTTP failure',async()=>{
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({start(controller){controller.enqueue(new Uint8Array(8193));},cancel(){cancelled=true;}});
    await assert.rejects(requireAssetResponse(new Response(body,{status:502,headers:{'Content-Type':'application/json'}}),'FST'),/HTTP 502\.$/);
    assert.equal(cancelled,true);
    await assert.rejects(requireAssetResponse(new Response('{invalid',{status:502,headers:{'Content-Type':'application/json'}}),'FST'),/HTTP 502\.$/);
    await assert.rejects(requireAssetResponse(new Response('{"error":"safe\\u0000notice"}',{status:502,headers:{'Content-Type':'application/json'}}),'FST'),/safe notice/);
});
