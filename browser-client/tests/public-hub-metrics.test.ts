// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
// The diagnostic-only helper is ordinary JavaScript, not part of the frontend.
// @ts-expect-error Dedicated runtime helper has no frontend declaration.
import {assetCategory,assetCategoryTotals,assetSessionTotals,requireWorldLoadingReady} from './integration/public-hub-metrics.mjs';

test('asset categories derive only extension from requested pathname, preserving query/fragment privacy',()=>{
  for(const [url,expected] of [
    ['https://assets.example/Model.FBX?token=private#selector','FBX'],
    ['atp:/avatar.fst','FST'],['https://assets.example/a%2Efbx','FBX'],
    ['https://assets.example/mesh.baked.fbx.json','JSON'],['https://assets.example/image.texmeta.json','texmeta'],['https://assets.example/texmeta.json','JSON'],['https://assets.example/IMG.PSD?name=other.fbx','image'],
    ['https://assets.example/texture.dds','image'],['https://assets.example/texture.ktx2','image'],
    ['https://assets.example/texture.tga','image'],['https://assets.example/file.glb?asset=image.png','other'],
    ['invalid','other'],['https://assets.example/%xx.png','other'],
  ])assert.equal(assetCategory(url),expected);
});
test('per-category duplicate counts and source counters do not mix URL identities or expose them',()=>{
  const totals=assetCategoryTotals([
    {category:'FBX',requests:3,knownBytes:12,unknownByteResponses:0,sources:{download:1,shared:1,memory:1,unknown:0},url:'must-not-be-published'},
    {category:'FBX',requests:1,knownBytes:0,unknownByteResponses:1,sources:{unknown:1}},
    {category:'__proto__',requests:1,knownBytes:0,unknownByteResponses:1,sources:{unknown:1}},
    {category:'image',requests:2,knownBytes:8,unknownByteResponses:0,sources:{download:1,memory:1}},
  ]);
  assert.deepEqual(totals.FBX,{uniqueURLs:2,requests:4,duplicateRequests:2,knownBytes:12,unknownByteResponses:1,sources:{download:1,shared:1,memory:1,unknown:1}});
  assert.equal(totals.image.duplicateRequests,1);assert.equal(totals.other.requests,1);assert.equal(Object.hasOwn(Object.prototype,'requests'),false);
  assert.doesNotMatch(JSON.stringify(totals),/must-not-be-published/);
});

test('fresh session ordinals separate repeated world loading without publishing native session IDs',()=>{
  const item={category:'FBX',urlSHA256:'a'.repeat(64),requests:2,knownBytes:8,unknownByteResponses:0,totalMs:12,maximumMs:8,sources:{download:1,memory:1},privateSessionId:'SECRET-SESSION-ID'};
  const sessions=assetSessionTotals([
    {...item,ordinal:2,requests:1,totalMs:4,maximumMs:4,sources:{download:1}},
    {...item,ordinal:1},
    {...item,ordinal:1,category:'image',urlSHA256:'b'.repeat(64),requests:3,totalMs:15,maximumMs:6,sources:{download:1,memory:2}},
  ]);
  assert.equal(sessions.length,2);assert.equal(sessions[0].ordinal,1);assert.equal(sessions[1].ordinal,2);
  assert.equal(sessions[0].uniqueURLs,2);assert.equal(sessions[0].requests,5);assert.equal(sessions[0].duplicateRequests,3);
  assert.equal(sessions[0].totalRequestMs,27);assert.equal(sessions[0].maximumRequestMs,8);
  assert.equal(sessions[1].uniqueURLs,1);assert.equal(sessions[1].duplicateRequests,0);
  assert.equal(sessions[0].categories.FBX.duplicateRequests,1);assert.equal(sessions[0].categories.image.duplicateRequests,2);
  assert.equal(sessions[1].categories.FBX.duplicateRequests,0);
  assert.doesNotMatch(JSON.stringify(sessions),/SECRET-SESSION-ID|privateSessionId/);
  assert.throws(()=>assetSessionTotals([{...item,ordinal:NaN}]),/ordinal/);
});

test('elapsed loading deadline cannot turn pending, absent or empty world models into completed acceptance',()=>{
  const ready={loadedModels:297,queuedModels:0,loadingModels:0,compilingGraphics:0};
  assert.doesNotThrow(()=>requireWorldLoadingReady(ready));
  for(const pending of [{...ready,queuedModels:1},{...ready,loadingModels:1},{...ready,compilingGraphics:1},{...ready,loadedModels:0},undefined])
    assert.throws(()=>requireWorldLoadingReady(pending),/existing deadline/);
});
