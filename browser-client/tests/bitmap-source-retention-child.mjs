// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// CPU-only positive WeakRef ownership check; no browser pixels/performance claim.
import assert from 'node:assert/strict';
import {Texture} from 'three';
import {WorldBitmapUpload} from '../src/world-bitmap-upload.ts';
assert.equal(typeof globalThis.gc,'function');
const abort=new AbortController(),owner=new WorldBitmapUpload({signal:abort.signal,isImage:()=>true,createBitmap:async()=>({width:2,height:2,close(){}})});
async function prepare(){const original=new Texture({naturalWidth:2,naturalHeight:2}),source=new WeakRef(original.source),image=new WeakRef(original.image),prepared=await owner.prepare(original,abort.signal);return{source,image,prepared};}
const result=await prepare();
for(let attempt=0;attempt<20;attempt++){await new Promise(resolve=>setImmediate(resolve));globalThis.gc();await new Promise(resolve=>setImmediate(resolve));if(!result.source.deref()&&!result.image.deref())break;}
assert.equal(result.source.deref(),undefined,'Ready bitmap cache retained original borrowed Texture Source');assert.equal(result.image.deref(),undefined,'Ready bitmap cache retained original decoded HTML image');
assert(owner.isCurrent(result.prepared));assert.equal(owner.stats().retainedEntries,1);assert.equal(owner.stats().leases,1);abort.abort();result.prepared.dispose();assert.equal(owner.stats().bytes,0);
console.log(JSON.stringify({originalSourceCollected:true,originalImageCollected:true,livePreparedSamplerPreserved:true,bytesAfterClose:owner.stats().bytes}));
