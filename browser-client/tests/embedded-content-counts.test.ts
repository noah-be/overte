// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';
import {embeddedContentCounts} from '../src/embedded-content-counts';
import {EmbeddedFbxImages} from '../src/embedded-fbx-images';
const hash='a'.repeat(64),record=(owner:number,bytes=4,mime='image/png',digest=hash)=>({key:`${owner}|${mime}|${digest}`,bytes});
test('byte identities distinguish repeated owners from different MIME/content without disclosing identities',()=>{
 assert.deepEqual(embeddedContentCounts([record(1),record(2),record(3,8,'image/jpeg'),record(4,12,'image/png','b'.repeat(64))]),{distinctContents:3,repeatedContentEntries:1,distinctContentBytes:24,repeatedContentBytes:4});
 assert.deepEqual(embeddedContentCounts([]),{distinctContents:0,repeatedContentEntries:0,distinctContentBytes:0,repeatedContentBytes:0});
 assert.equal(JSON.stringify(embeddedContentCounts([record(1)] )).includes(hash),false);
});
test('snapshot metadata is bounded even for adversarial iterable/identity/byte values',()=>{
 assert.throws(()=>embeddedContentCounts((function*(){while(true)yield record(1);})()),/256 entries/);
 for(const bad of [{key:'x'.repeat(129),bytes:4},{key:'https://private.invalid',bytes:4},record(1,0),record(1,8*1024*1024+1)])assert.throws(()=>embeddedContentCounts([bad]));
 assert.throws(()=>embeddedContentCounts([record(1),record(2,5)]),/Inconsistent/);
 assert.throws(()=>embeddedContentCounts(Array.from({length:17},(_,i)=>record(i+1,8*1024*1024))),/128 MiB/);
});
test('actual registry observer counts only its existing approved leases and never crosses visitor worlds',()=>{
 const a=new AbortController(),b=new AbortController(),first=new EmbeddedFbxImages(a.signal),second=new EmbeddedFbxImages(b.signal),image={digest:hash,mimeType:'image/png',bytes:new ArrayBuffer(4)};
 const one=first.register(new ArrayBuffer(1),[image],a.signal),two=first.register(new ArrayBuffer(1),[image],a.signal),other=second.register(new ArrayBuffer(1),[image],b.signal),marker=`data:image/png;base64,overte-embedded-${hash}`;
 one.resolveURL(marker);two.resolveURL(marker);other.resolveURL(marker);
 assert.equal(first.statistics.entries,2);assert.equal(first.statistics.distinctContents,1);assert.equal(first.statistics.repeatedContentEntries,1);assert.equal(first.statistics.repeatedContentBytes,4);
 assert.equal(second.statistics.entries,1);assert.equal(second.statistics.repeatedContentEntries,0);
 a.abort();assert.equal(first.statistics.distinctContents,0);assert.equal(second.statistics.distinctContents,1);b.abort();
});
