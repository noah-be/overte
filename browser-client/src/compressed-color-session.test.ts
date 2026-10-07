// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CompressedColorSession} from './compressed-color-session';
import type {ServerMessage,SessionCallbacks} from './session';
const caps={s3tc:true,s3tcSRGB:true,maximumTextureSize:32768};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
function bytes(){
 const data=new Uint8Array(64+52+4+8),view=new DataView(data.buffer);data.set([0xab,0x4b,0x54,0x58,0x20,0x31,0x31,0xbb,13,10,26,10]);
 [0x04030201,0,1,0,0x8c4c,0x1907,4,4,0,0,1,1,52].forEach((n,i)=>view.setUint32(12+i*4,n,true));
 view.setUint32(64,45,true);data.set(new TextEncoder().encode('hifi.gpu\0'),68);data[77]=1;view.setUint32(77+29,1,true);view.setUint32(116,8,true);return data;
}
function response(){return new Response(bytes());}
class Socket {
 static OPEN=1;static instances:Socket[]=[];readyState=0;bufferedAmount=0;binaryType='blob';
 onopen?:()=>void;onmessage?:(event:{data:string})=>void;onerror?:()=>void;onclose?:(event:{reason:string})=>void;sent:string[]=[];closeCode?:number;
 constructor(public url:URL){Socket.instances.push(this);}
 open(){this.readyState=1;this.onopen?.();}
 deliver(message:unknown){this.onmessage?.({data:JSON.stringify(message)});}
 send(text:string){this.sent.push(text);}
 close(code?:number,reason=''){this.readyState=3;this.closeCode=code;this.onclose?.({reason});}
}
async function environment(run:(create:(extra?:Partial<SessionCallbacks>)=>CompressedColorSession)=>Promise<void>){
 const originals=new Map(['window','WebSocket'].map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));Socket.instances=[];
 Object.defineProperty(globalThis,'window',{configurable:true,value:{location:{href:'https://client.example/client'}}});
 Object.defineProperty(globalThis,'WebSocket',{configurable:true,value:Socket});const sessions:CompressedColorSession[]=[];
 try{await run(extra=>{const session=new CompressedColorSession({message:()=>{},error:()=>{},closed:()=>{},audio:()=>{},...extra});sessions.push(session);return session;});}
 finally{for(const session of sessions)session.leave();for(const [name,descriptor]of originals){if(descriptor)Object.defineProperty(globalThis,name,descriptor);else Reflect.deleteProperty(globalThis,name);}}
}
function joined(session:CompressedColorSession,id='session-one',revision=1){session.join('overte://allowed.example','Visitor');const socket=Socket.instances.at(-1)!;socket.open();socket.deliver({type:'state',state:'connecting',sessionId:id});socket.deliver({type:'state',state:'connected',sessionId:id,permissionRevision:revision});return socket;}

test('raw asset snapshots revoke before callbacks and every reapproval receives a fresh source generation',async()=>environment(async create=>{
 const session=create();assert.throws(()=>session.captureAssetAuthority(),/connected session authority/);const socket=joined(session),first=session.captureAssetAuthority();first.assertCurrent();
 socket.deliver({type:'state',state:'connecting',sessionId:'session-one'});assert.throws(first.assertCurrent,/revoked/);assert.throws(()=>session.captureAssetAuthority(),/connected session authority/);
 socket.deliver({type:'state',state:'connected',sessionId:'session-one',permissionRevision:1});const second=session.captureAssetAuthority();assert.notEqual(first.generation,second.generation);assert.throws(first.assertCurrent,/revoked/);second.assertCurrent();
 socket.deliver({type:'state',state:'connected',sessionId:'session-one',permissionRevision:2});const third=session.captureAssetAuthority();assert.notEqual(second.generation,third.generation);assert.throws(second.assertCurrent,/revoked/);third.assertCurrent();session.leave();assert.throws(third.assertCurrent,/revoked/);
}));

test('actual BrowserSession lifecycle grants only connected metadata; Tablet revisions and pending sessions cannot grant a cache',async()=>environment(async create=>{
 const session=create(),world=new AbortController(),revision=()=>session.compressedAssetApproval?.permissionRevision;session.join('overte://allowed.example','Visitor');const socket=Socket.instances.at(-1)!;socket.open();
 socket.deliver({type:'state',state:'connecting',sessionId:'session-one'});assert.throws(()=>session.compressedColors(caps,world.signal),/connected session authority/);
 socket.deliver({type:'tablet',kind:'state',revision:99,visible:false,screen:'Home',loading:false});assert.equal(session.compressedAssetApproval,undefined);
 socket.deliver({type:'state',state:'connected',sessionId:'session-one',permissionRevision:3});assert.equal(revision(),3);
 socket.deliver({type:'tablet',kind:'state',revision:99,visible:false,screen:'Home',loading:false});assert.equal(revision(),3);
 const requested:string[]=[];const cache=session.compressedColors(caps,world.signal,{fetch:(async(url,options)=>{requested.push(String(url));assert.equal(options?.credentials,'same-origin');return response();}) as typeof fetch});
 const texture=await cache.load('https://assets.example/map.ktx');texture.dispose();assert.equal(new URL(requested[0]).pathname,'/api/assets/session-one');assert.equal(new URL(requested[0]).searchParams.get('url'),'https://assets.example/map.ktx');
 assert.equal(session.compressedColors(caps,world.signal),cache);world.abort();await assert.rejects(cache.load('another'),{name:'AbortError'});
}));
test('Leave revokes before socket sends; old socket messages cannot approve a fresh domain session',async()=>environment(async create=>{
 const session=create(),world=new AbortController(),first=joined(session);
 const cache=session.compressedColors(caps,world.signal,{fetch:(async()=>response()) as typeof fetch});(await cache.load('map')).dispose();await tick();
 const send=first.send.bind(first);first.send=text=>{assert.equal(session.compressedAssetApproval,undefined);assert.equal(cache.statistics.retainedBytes,0);send(text);};session.leave();
 assert.equal(session.compressedAssetApproval,undefined);await assert.rejects(cache.load('map'),{name:'AbortError'});
 session.join('overte://different.example','Other visitor');const second=Socket.instances.at(-1)!;second.open();first.deliver({type:'state',state:'connected',sessionId:'session-one',permissionRevision:50});
 assert.equal(session.compressedAssetApproval,undefined);second.deliver({type:'state',state:'connected',sessionId:'session-two',permissionRevision:1});
 const fresh=session.compressedColors(caps,new AbortController().signal,{fetch:(async url=>{assert.equal(new URL(String(url)).pathname,'/api/assets/session-two');return response();}) as typeof fetch});assert.notEqual(fresh,cache);(await fresh.load('map')).dispose();
}));
test('denied and transient states revoke synchronously before app callbacks, and same revision reapproval never reuses old bytes',async()=>environment(async create=>{
 let previous:ReturnType<CompressedColorSession['compressedColors']>|undefined;const notices:ServerMessage[]=[];
 const session=create({message:message=>{if(message.type==='state'&&message.state!=='connected'&&previous){assert.equal(previous.statistics.retainedBytes,0);assert.equal(session.compressedAssetApproval,undefined);}notices.push(message);}});
 const socket=joined(session),world=new AbortController();let requests=0;const fetcher=(async()=>{requests++;return response();}) as typeof fetch;
 previous=session.compressedColors(caps,world.signal,{fetch:fetcher});(await previous.load('map')).dispose();await tick();
 const oldEpoch=session.compressedAssetApproval!.epoch;socket.deliver({type:'state',state:'connecting',sessionId:'session-one'});await assert.rejects(previous.load('map'),{name:'AbortError'});
 socket.deliver({type:'state',state:'connected',sessionId:'session-one',permissionRevision:1});assert.ok(session.compressedAssetApproval!.epoch>oldEpoch);
 const next=session.compressedColors(caps,world.signal,{fetch:fetcher});assert.notEqual(next,previous);(await next.load('map')).dispose();await tick();previous=next;
 socket.deliver({type:'state',state:'error',message:'Domain access refused.'});assert.throws(()=>session.compressedColors(caps,world.signal),/connected session authority/);assert.equal(requests,2);assert.equal(notices.at(-1)?.type,'state');
}));
test('an uncancellable retired request blocks replacement allocation until actual completion',async()=>environment(async create=>{
 const session=create(),socket=joined(session),world=new AbortController(),pending=deferred<Response>();let requests=0;
 const cache=session.compressedColors(caps,world.signal,{fetch:(async()=>{requests++;return pending.promise;}) as typeof fetch});const loading=cache.load('map');
 socket.deliver({type:'state',state:'connecting',sessionId:'session-one'});await assert.rejects(loading,{name:'AbortError'});assert.equal(cache.statistics.active,1);
 socket.deliver({type:'state',state:'connected',sessionId:'session-one',permissionRevision:2});assert.throws(()=>session.compressedColors(caps,world.signal),/previous compressed asset readers/);assert.equal(requests,1);
 pending.resolve(response());await tick();assert.equal(cache.statistics.active,0);
 const replacement=session.compressedColors(caps,world.signal,{fetch:(async()=>{requests++;return response();}) as typeof fetch});(await replacement.load('map')).dispose();assert.equal(requests,2);
}));
test('missing authority, unexpected session changes and protocol failures cannot expose cache bytes',async()=>environment(async create=>{
 for(const metadata of [{sessionId:'session-one'},{permissionRevision:1},{sessionId:'different-session',permissionRevision:1}]){
  const errors:string[]=[],session=create({error:error=>errors.push(error)});session.join('overte://allowed.example','Visitor');const socket=Socket.instances.at(-1)!;socket.open();socket.deliver({type:'state',state:'connecting',sessionId:'session-one'});
  socket.deliver({type:'state',state:'connected',...metadata});assert.equal(session.compressedAssetApproval,undefined);assert.equal(socket.closeCode,4002);assert.equal(errors.length,1);assert.throws(()=>session.compressedColors(caps,new AbortController().signal),/connected session authority/);
 }
 const session=create(),socket=joined(session),world=new AbortController(),cache=session.compressedColors(caps,world.signal,{fetch:(async()=>response()) as typeof fetch});
 (await cache.load('map')).dispose();await tick();socket.deliver({type:'unsupported'});assert.equal(session.compressedAssetApproval,undefined);assert.equal(cache.statistics.retainedBytes,0);assert.equal(socket.closeCode,4002);
}));
