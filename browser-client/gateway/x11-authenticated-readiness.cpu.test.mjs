// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// CPU-only contracts: execute the production function body,
// inject event transport and timers only; never import or launch a worker/service.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {EventEmitter,getEventListeners} from 'node:events';
import vm from 'node:vm';
const source=await readFile(new URL('./worker-sandbox.mjs',import.meta.url),'utf8');
const begin=source.indexOf('function privateX11Ready(');
const end=source.indexOf('\nconst runtimeVariables',begin);
assert(begin>=0&&end>begin);
assert.equal(source.split('function privateX11Ready(').length,2);
const body=source.slice(begin,end).trim();
for(const [scenario,expected]of[['fragmented','authenticated'],['refused','refused'],['wrong-version','invalid-setup'],['wrong-minor','invalid-setup'],['short-length','invalid-setup'],['oversized','invalid-setup'],['fragmented-oversized','invalid-setup'],['socket-error','socket-error'],['closed','closed'],['timeout','timeout'],['aborted','cancelled'],['pre-aborted','cancelled']]){
 test('authenticated X11 readiness: '+scenario,async()=>{
  const cookie=Buffer.from('private-CPU-only');const c=new AbortController();let socket,timer,cleared=0,writes=0;
  if(scenario==='pre-aborted')c.abort();
  class Transport extends EventEmitter{
   write(b){writes++;assert.equal(b.length,48);assert.equal(b[0],108);assert.equal(b.readUInt16LE(2),11);assert.equal(b.readUInt16LE(4),0);assert.equal(b.readUInt16LE(6),18);assert.equal(b.readUInt16LE(8),16);assert.deepEqual(b.subarray(10,12),Buffer.alloc(2));assert.equal(b.subarray(12,30).toString(),'MIT-MAGIC-COOKIE-1');assert.deepEqual(b.subarray(30,32),Buffer.alloc(2));assert(b.subarray(32).equals(cookie));}
   destroy(){this.destroyed=true;}
  }
  const connect=p=>{assert.equal(p,'/tmp/.X11-unix/X1234');socket=new Transport();queueMicrotask(()=>{
   socket.emit('connect');const r=Buffer.alloc(40);r[0]=1;r.writeUInt16LE(11,2);r.writeUInt16LE(8,6);
   if(scenario==='fragmented'){socket.emit('data',r.subarray(0,3));assert(!socket.destroyed);socket.emit('data',r.subarray(3,8));assert(!socket.destroyed);socket.emit('data',r.subarray(8));}
   else if(scenario==='refused'){r[0]=0;socket.emit('data',r);}
   else if(scenario==='wrong-version'){r.writeUInt16LE(12,2);socket.emit('data',r);}
   else if(scenario==='wrong-minor'){r.writeUInt16LE(1,4);socket.emit('data',r);}
   else if(scenario==='short-length'){r.writeUInt16LE(7,6);socket.emit('data',r);}
   else if(scenario==='oversized')socket.emit('data',Buffer.alloc(65537));
   else if(scenario==='fragmented-oversized'){const head=Buffer.alloc(8);head[0]=1;head.writeUInt16LE(11,2);head.writeUInt16LE(16382,6);socket.emit('data',head);assert(!socket.destroyed);socket.emit('data',Buffer.alloc(65529));}
   else if(scenario==='socket-error')socket.emit('error',Error('private-CPU-only'));
   else if(scenario==='closed')socket.emit('close');
   else if(scenario==='aborted')c.abort();else timer();
  });return socket;};
  const ready=vm.runInNewContext('('+body+')',{Buffer,createConnection:connect,setTimeout(fn,ms){assert.equal(ms,5000);timer=fn;return 1;},clearTimeout(){cleared++;}});
  assert.equal(await ready(1234,cookie,c.signal,5000),expected);assert.equal(getEventListeners(c.signal,'abort').length,0);
  if(socket){assert(socket.destroyed);assert.equal(writes,1);assert.equal(cleared,1);timer();socket.emit('close');assert.equal(cleared,1);}else{assert.equal(scenario,'pre-aborted');assert.equal(cleared,0);}
 });
}
test('authenticated X11 readiness rejects unknown display/cookie/deadline before transport',()=>{
 const ready=vm.runInNewContext('('+body+')',{Buffer,createConnection(){assert.fail('transport called');},setTimeout(){assert.fail('timer called');}});
 for(const [d,k,t]of[[1199,Buffer.alloc(16),5000],[60000,Buffer.alloc(16),5000],[1234,Buffer.alloc(15),5000],[1234,Buffer.alloc(17),5000],[1234,'not-a-cookie',5000],[1234,Buffer.alloc(16),0],[1234,Buffer.alloc(16),5001]])assert.throws(()=>ready(d,k,new AbortController().signal,t),/Invalid private display readiness scope/);
});
