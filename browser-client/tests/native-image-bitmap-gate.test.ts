// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';import {createNativeImageBitmapGate} from './native-image-bitmap-gate';
function fakeBitmap(){let closes=0;const value={width:8,height:8,close(){closes++;value.width=value.height=0;}};return {bitmap:value as ImageBitmap,count:()=>closes};}
function deferred<T>(){let resolve!:(value:T)=>void,reject!:(error:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
test('a real-factory result arriving after fixture cleanup is closed and returned without a held orphan',async()=>{
 const source={},factory=deferred<ImageBitmap>(),{bitmap,count}=fakeBitmap();const gate=createNativeImageBitmapGate(()=>source,(()=>factory.promise) as typeof createImageBitmap);
 const pending=gate.invoke(source as ImageBitmap);gate.close();factory.resolve(bitmap);
 assert.equal(await pending,bitmap);assert.equal(await gate.ready,bitmap);assert.equal(count(),1);assert.equal(bitmap.width,0);gate.close();assert.equal(count(),1);
});
test('fixture cleanup releases an already-produced held bitmap even without ordinary delivery',async()=>{
 const source={},{bitmap,count}=fakeBitmap(),gate=createNativeImageBitmapGate(()=>source,(async()=>bitmap) as typeof createImageBitmap);
 const pending=gate.invoke(source as ImageBitmap);assert.equal(await gate.ready,bitmap);gate.close();assert.equal(await pending,bitmap);assert.equal(count(),1);
});
test('ordinary delivery transfers bitmap ownership and subsequent cleanup never closes the consumer bitmap',async()=>{
 const source={},{bitmap,count}=fakeBitmap(),gate=createNativeImageBitmapGate(()=>source,(async()=>bitmap) as typeof createImageBitmap);
 const pending=gate.invoke(source as ImageBitmap);await gate.ready;gate.deliver();assert.equal(await pending,bitmap);gate.close();assert.equal(count(),0);bitmap.close();assert.equal(count(),1);
});
test('unrelated bitmap calls are never held, claimed, or closed by fixture teardown',async()=>{
 const source={},other={},{bitmap,count}=fakeBitmap(),gate=createNativeImageBitmapGate(()=>source,(async()=>bitmap) as typeof createImageBitmap);
 assert.equal(await gate.invoke(other as ImageBitmap),bitmap);gate.close();assert.equal(count(),0);bitmap.close();
});
test('a failing real factory rejects both owned invocation and ready boundary without hanging cleanup',async()=>{
 const source={},failure=Error('real bitmap failed'),gate=createNativeImageBitmapGate(()=>source,(async()=>{throw failure;}) as typeof createImageBitmap);
 await Promise.all([assert.rejects(gate.invoke(source as ImageBitmap),error=>error===failure),assert.rejects(gate.ready,error=>error===failure)]);gate.close();
});
test('a second owned request cannot create additional held image work',async()=>{
 const source={},{bitmap,count}=fakeBitmap(),gate=createNativeImageBitmapGate(()=>source,(async()=>bitmap) as typeof createImageBitmap);
 const pending=gate.invoke(source as ImageBitmap);await gate.ready;await assert.rejects(gate.invoke(source as ImageBitmap),/already has an owned request/);gate.close();await pending;assert.equal(count(),1);
});
