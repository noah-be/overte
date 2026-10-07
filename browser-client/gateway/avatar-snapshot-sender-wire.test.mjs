// SPDX-License-Identifier: Apache-2.0
// OWN loopback CPU WebSockets only. No native/browser/service or outside socket.
import test from 'node:test';import assert from 'node:assert/strict';
import WebSocket,{WebSocketServer}from'ws';import{performance}from'node:perf_hooks';
import{AvatarSnapshotSender as AvatarSenderPrototype,MAX_BUFFER}from'./avatar-snapshot-sender.mjs';
import{pose,parse,oldSend}from'./avatar-snapshot-fixture.mjs';
function boundedOwn(promise, stage) {
 let timer;const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('own-fixture-'+stage+'-timeout')),5000);});
 return Promise.race([promise,timeout]).finally(()=>clearTimeout(timer));
}
function message(target){const m=pose(target),names=Array.from({length:300},(_,i)=>'joint-'+i+'-'+('a'.repeat(220)));for(const a of m.avatars){a.jointNames=names;a.jointRotations=names.map(()=>({x:0,y:0,z:0,w:1}));a.jointTranslations=names.map(()=>({x:0,y:0,z:0}));}return m;}
async function lane(candidate){
 const wss=new WebSocketServer({host:'127.0.0.1',port:0,perMessageDeflate:false,maxPayload:16*1024*1024});
 await boundedOwn(new Promise((resolve,reject)=>{wss.once('listening',resolve);wss.once('error',reject);}), 'listen');
 const peerP=new Promise(resolve=>wss.once('connection',resolve)),client=new WebSocket('ws://127.0.0.1:'+wss.address().port);
 let peer,stream,emitTimer,resumeTimer;const peers=new Set();wss.on('connection',p=>{peers.add(p);p.once('close',()=>peers.delete(p));});
 const report={candidate,originalTargetWindowMs:2800,fullParserValidation:true,warmupOffers:70,targetOffers:0,observedWrites:0,observedBlocked:0,maxBufferedBytes:0,maxPhysicalInFlight:0,maxPending:0,targetWithinWindow:false,ownedClosed:false};
 try{
  await boundedOwn(new Promise((resolve,reject)=>{client.once('open',resolve);client.once('error',reject);}), 'open');peer=await boundedOwn(peerP,'peer');
  const owner={browser:peer,native:{},permissionRevision:1,permissionsApproved:true,closed:false,isCurrent:()=>true};
  const observe=(...args)=>{const open=candidate?args[0].open:args[0],bytes=candidate?args[0].bytes:args[1],write=candidate?args[0].writeInvoked:args[2];if(write)report.observedWrites++;else if(open&&bytes>=MAX_BUFFER)report.observedBlocked++;report.maxBufferedBytes=Math.max(report.maxBufferedBytes,bytes||0);};
  stream=candidate?new AvatarSenderPrototype(peer,()=>owner,observe):null;
  const offer=value=>{if(candidate){stream.offer(owner,value,Math.floor(performance.now()));const b=stream.bounds();report.maxPhysicalInFlight=Math.max(report.maxPhysicalInFlight,b.physicalInFlight);report.maxPending=Math.max(report.maxPending,b.latestPending);}else oldSend(peer,value,observe);};
  // Pause then slowly consume actual TCP bytes. It is fixture behavior, not a
  // modified Core wait/assertion or a production scheduling recommendation.
  client._socket.pause();client._socket.on('data',()=>{client._socket.pause();clearTimeout(resumeTimer);resumeTimer=setTimeout(()=>client._socket.resume(),60);});
  const old=message({x:3,y:1.8,z:3}),target=message({x:4,y:1.8,z:2});
  parse(JSON.stringify(old));parse(JSON.stringify(target));report.completeMessageBytes=Buffer.byteLength(JSON.stringify(target));
  let start;let resolveTarget;const targetP=new Promise(resolve=>{resolveTarget=resolve;});
  client.on('message',data=>{const m=parse(data.toString());if(m.avatars[1].position.x===4&&m.avatars[1].position.z===2&&report.targetObservedMs===undefined){report.targetObservedMs=performance.now()-start;resolveTarget();}});
  for(let i=0;i<70;i++)offer(old);
  start=performance.now();offer(target);report.targetOffers++;
  emitTimer=setInterval(()=>{offer(target);report.targetOffers++;},50); // existing producer20Hz model
  resumeTimer=setTimeout(()=>client._socket.resume(),800);
  let timeout;const expired=new Promise(resolve=>{timeout=setTimeout(resolve,2800);});
  report.targetWithinWindow=await Promise.race([targetP.then(()=>true),expired.then(()=>false)]);clearTimeout(timeout);
 }finally{
  clearInterval(emitTimer);clearTimeout(resumeTimer);stream?.close();
  const clientGone=new Promise(resolve=>client.readyState===WebSocket.CLOSED?resolve():client.once('close',resolve));
  const peerGone=new Promise(resolve=>!peer||peer.readyState===WebSocket.CLOSED?resolve():peer.once('close',resolve));
  client.terminate();peer?.terminate();for(const p of peers)p.terminate();
  await boundedOwn(Promise.all([clientGone,peerGone]),'endpoints-close');await boundedOwn(new Promise(resolve=>wss.close(resolve)),'server-close');
  assert.equal(peers.size,0);assert.equal(wss.clients.size,0);report.ownedClosed=true;
 }
 return report;
}
test('real low-consumption wire original stale versus newest-complete prototype within original2800',async()=>{
 const old=await lane(false),candidate=await lane(true);
 assert.equal(old.targetWithinWindow,false,'original overload control must reproduce refusal/stale target');
 assert(old.observedBlocked>0);assert(old.maxBufferedBytes>=MAX_BUFFER);
 assert.equal(candidate.targetWithinWindow,true);assert.equal(candidate.maxPhysicalInFlight,1);assert.equal(candidate.maxPending,1);
 assert(old.ownedClosed&&candidate.ownedClosed);
 console.log('FIXED_OWN_WS '+JSON.stringify({old,candidate,hostedCauseEstablished:false,productionQualified:false}));
});
