// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {GpuTimeObserver} from './gpu-time-observer';

function fixture(options:{supported?:boolean;bits?:number;maxPending?:number;timeoutMs?:number}={}){
 let time=0,current:WebGLQuery|null=null,disjoint=false,lost=false,reads=0,ends=0,created=0,warnings=0;
 const available=new Set<WebGLQuery>(),values=new Map<WebGLQuery,number>(),deleted:WebGLQuery[]=[];
 const extension={TIME_ELAPSED_EXT:10,GPU_DISJOINT_EXT:11,QUERY_COUNTER_BITS_EXT:12};
 const gl={CURRENT_QUERY:1,QUERY_RESULT_AVAILABLE:2,QUERY_RESULT:3,getExtension:()=>options.supported===false?null:extension,
  getQuery:(_target:number,key:number)=>key===12?options.bits??64:current,
  createQuery:()=>{created++;return {} as WebGLQuery;},beginQuery:(_target:number,query:WebGLQuery)=>{assert.equal(current,null);current=query;},endQuery:()=>{ends++;current=null;},
  isContextLost:()=>lost,getParameter:()=>disjoint,getQueryParameter:(query:WebGLQuery,key:number)=>{if(key===2)return available.has(query);assert(available.has(query),'Result read cannot block before availability');reads++;return values.get(query)??1200000;},
  deleteQuery:(query:WebGLQuery)=>{assert(!deleted.includes(query),'Each owned query is released only once');deleted.push(query);},
 };
 const observer=new GpuTimeObserver(gl as unknown as WebGL2RenderingContext,{maxPending:options.maxPending,timeoutMs:options.timeoutMs,now:()=>time,onWarning(){warnings++;}});
 return {observer,gl,deleted,available,values,get current(){return current;},get reads(){return reads;},get ends(){return ends;},get created(){return created;},get warnings(){return warnings;},advance(value:number){time+=value;},ready(query:WebGLQuery,value=1200000){available.add(query);values.set(query,value);},external(query:WebGLQuery|null){current=query;},disjoint(){disjoint=true;},lost(){lost=true;}};
}

test('unavailable extension/unsafe counters expose unsupported rather than invented zero timings',()=>{
 for(const options of [{supported:false},{bits:0},{bits:16}]){const f=fixture(options);assert.equal(f.observer.begin(),false);assert.equal(f.created,0);assert.equal(f.observer.getSnapshot().supported,false);assert.equal(f.observer.getSnapshot().completed,0);f.observer.dispose();}
 const f=fixture({bits:32});assert.equal(f.observer.getSnapshot().timeoutMs,2147);f.observer.dispose();
});
test('asynchronous availability gates nanosecond result reads and preserves full precision',()=>{
 const f=fixture();assert.equal(f.observer.begin(),true);const query=f.current!;assert.equal(f.observer.end(),true);
 f.observer.poll();assert.equal(f.reads,0);assert.equal(f.observer.getSnapshot().pending,1);
 f.ready(query,2500000123);f.advance(2600);f.observer.poll();assert.equal(f.reads,1);assert.equal(f.observer.getSnapshot().completed,1);assert.equal(f.observer.getSnapshot().totalGpuMs,2500.000123);assert.equal(f.deleted.length,1);f.observer.dispose();
});
test('pending-query cap and deadline bound resources without synchronous waits',()=>{
 const f=fixture({maxPending:2,timeoutMs:100});
 for(let i=0;i<2;i++){assert(f.observer.begin());assert(f.observer.end());}
 assert.equal(f.observer.begin(),false);assert.equal(f.created,2);assert.equal(f.observer.getSnapshot().peakQueries,2);
 f.advance(100);f.observer.poll();assert.equal(f.observer.getSnapshot().timedOut,2);assert.equal(f.reads,0);assert.equal(f.deleted.length,2);assert(f.observer.begin());f.observer.dispose();assert.equal(f.deleted.length,3);
});
test('disjoint invalidates every owned pending/active query without reading results',()=>{
 const f=fixture();assert(f.observer.begin());const old=f.current!;assert(f.observer.end());assert(f.observer.begin());f.ready(old);f.disjoint();f.observer.poll();
 assert.equal(f.reads,0);assert.equal(f.deleted.length,2);assert.equal(f.ends,2);assert.equal(f.observer.getSnapshot().disjointDropped,2);assert.equal(f.observer.getSnapshot().completed,0);f.observer.dispose();
});
test('foreign active timer query is preserved on begin and ownership-loss disposal',()=>{
 const f=fixture(),foreign={} as WebGLQuery;f.external(foreign);assert.equal(f.observer.begin(),false);assert.equal(f.observer.getSnapshot().skippedExternal,1);assert.equal(f.current,foreign);assert.equal(f.created,0);
 f.external(null);assert(f.observer.begin());const owned=f.current!;f.external(foreign);assert.equal(f.observer.end(),false);assert.equal(f.current,foreign);assert.equal(f.ends,0);assert.deepEqual(f.deleted,[owned]);f.observer.dispose();assert.equal(f.current,foreign);
});
test('context loss and repeated disposal release owned handles without touching rendering',()=>{
 const f=fixture();assert(f.observer.begin());assert(f.observer.end());assert(f.observer.begin());f.lost();f.observer.poll();
 assert.equal(f.observer.getSnapshot().contextLost,true);assert.equal(f.deleted.length,2);assert.equal(f.observer.begin(),false);f.observer.dispose();f.observer.dispose();assert.equal(f.deleted.length,2);assert.equal(f.observer.getSnapshot().pending,0);
});
test('invalid result/fault cleanup remains bounded and warning is emitted once',()=>{
 const f=fixture();for(const value of [NaN,-1,Number.MAX_SAFE_INTEGER+1]){assert(f.observer.begin());const query=f.current!;assert(f.observer.end());f.ready(query,value);f.observer.poll();}
 assert.equal(f.observer.getSnapshot().failed,3);assert.equal(f.observer.getSnapshot().completed,0);assert.equal(f.warnings,1);
 assert(f.observer.begin());f.observer.end();f.gl.getQueryParameter=()=>{throw Error('Driver read failed');};f.observer.poll();f.observer.dispose();assert.equal(f.deleted.length,4);assert.equal(f.warnings,1);
});
test('constructor refuses unbounded options and an active query also expires',()=>{
 for(const options of [{maxPending:0},{maxPending:17},{timeoutMs:Infinity},{timeoutMs:10001}])assert.throws(()=>fixture(options),/bounded/);
 const f=fixture({timeoutMs:10});assert(f.observer.begin());f.advance(10);f.observer.poll();assert.equal(f.observer.getSnapshot().timedOut,1);assert.equal(f.ends,1);assert.equal(f.deleted.length,1);f.observer.dispose();
});
test('disjoint arising during availability or result access never enters timing totals',()=>{
 for(const phase of ['available','result']){
  const f=fixture();assert(f.observer.begin());const query=f.current!;f.observer.end();f.ready(query);
  const read=f.gl.getQueryParameter;f.gl.getQueryParameter=(value,key)=>{const result=read(value,key);if(key===(phase==='available'?2:3))f.disjoint();return result;};
  f.observer.poll();assert.equal(f.observer.getSnapshot().completed,0);assert.equal(f.observer.getSnapshot().totalGpuMs,0);assert.equal(f.observer.getSnapshot().disjointDropped,1);assert.equal(f.deleted.length,1);assert.equal(f.reads,phase==='available'?0:1);f.observer.dispose();
 }
});
test('a later driver fault releases remaining queries without double-deleting a completed query',()=>{
 const f=fixture();assert(f.observer.begin());const first=f.current!;f.observer.end();assert(f.observer.begin());const second=f.current!;f.observer.end();f.ready(first);f.ready(second);
 const read=f.gl.getQueryParameter;f.gl.getQueryParameter=(query,key)=>{if(query===second)throw Error('Driver failure after first result');return read(query,key);};
 f.observer.poll();assert.equal(f.observer.getSnapshot().completed,1);assert.equal(f.deleted.length,2);assert.equal(f.observer.getSnapshot().pending,0);f.observer.dispose();assert.equal(f.deleted.length,2);
});
test('pending queries expire without consuming a foreign timer disjoint flag',()=>{
 const f=fixture({timeoutMs:10});assert(f.observer.begin());f.observer.end();const foreign={} as WebGLQuery;f.external(foreign);f.advance(10);
 f.gl.getParameter=()=>{throw Error('Foreign global disjoint flag must not be consumed');};f.observer.poll();
 assert.equal(f.observer.getSnapshot().timedOut,1);assert.equal(f.observer.getSnapshot().failed,0);assert.equal(f.current,foreign);assert.equal(f.ends,1);assert.equal(f.deleted.length,1);f.observer.dispose();
});
