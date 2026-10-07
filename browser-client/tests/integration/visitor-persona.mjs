// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real fresh native workers against the isolated domain, without account/profile copying.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {WebSocket} from 'ws';
import {validateVisitorPersona} from '../../shared/visitor-persona.mjs';
const root=path.resolve(new URL('../../../',import.meta.url).pathname),port=8093,endpoint=`http://127.0.0.1:${port}`;
const input=JSON.parse(await readFile(path.join(root,'build/browser-hub-lab/gateway/environment-private.json'),'utf8'));
const nativeRoot=path.join(root,'build/browser-lab/appimage/squashfs-root');
const env={...(input.env||input),OVERTE_GATEWAY_PORT:String(port),OVERTE_GATEWAY_ORIGINS:endpoint,OVERTE_GATEWAY_MAX_SESSIONS:'1',
 OVERTE_INTERFACE:path.join(nativeRoot,'AppRun'),OVERTE_GATEWAY_NATIVE_ROOT:nativeRoot,OVERTE_GATEWAY_DOMAINS:'overte://127.0.0.2:45102',
 OVERTE_GATEWAY_GUEST_POLICY:path.join(root,'build/browser-lab/config/guest-policy.json'),OVERTE_GATEWAY_NATIVE_SCHEME:'hifi',
 OVERTE_GATEWAY_MANAGED_UDP_PORTS:'45102,45200,45201,45202,45203,45204,45205'};
delete env.OVERTE_GATEWAY_DEFAULT_SCRIPTS;
const directory=path.join(root,'build/browser-lab/persona-proof');await mkdir(directory,{recursive:true,mode:0o700});
const initial=validateVisitorPersona({displayName:'Visitor 世界 👋 '.repeat(12),avatarURL:'resource:/meshes/defaultAvatar_full.fst',avatarScale:1.2,
 avatarFavorites:['Persona 世界','__proto__','constructor','toString'].map(name=>({name,avatarURL:'resource:/meshes/defaultAvatar_full.fst',avatarScale:1.2,avatarIcon:'',avatarEntities:[]}))});
const files=['server.mjs','native-bridge.js','native-visitor-persona.js','visitor-persona.mjs'];
const hashes=async()=>Object.fromEntries(await Promise.all(files.map(async name=>[name,createHash('sha256').update(await readFile(path.join(root,'browser-client/gateway',name))).digest('hex')])));
const report={startedAt:new Date().toISOString(),domain:'isolated-managed-test-domain',nativeVersion:'2026.04.1',publicWorldMutations:0,microphoneEnabled:false,sourceSHA256:await hashes(),assertions:[],passed:false};
const gateway=spawn(process.execPath,[path.join(root,'browser-client/gateway/server.mjs')],{env,stdio:['ignore','pipe','pipe']});
let browser,timer,pose,persona,avatar,session,connected=false;const errors=[];
const wait=async(condition,timeout=90000)=>{const deadline=Date.now()+timeout;while(!condition()){if(errors.length)throw Error(errors[0]);if(Date.now()>deadline)throw Error('Actual native persona proof timed out');await new Promise(resolve=>setTimeout(resolve,50));}};
try{
 gateway.stderr.on('data',()=>{});await Promise.race([once(gateway.stdout,'data'),once(gateway,'exit').then(()=>{throw Error('Owned proof gateway failed startup');})]);
 const response=await fetch(endpoint+'/api/session'),cookie=response.headers.get('set-cookie').split(';')[0];await response.json();
 browser=new WebSocket(endpoint.replace('http:','ws:')+'/session',{headers:{Origin:endpoint,Cookie:cookie}});
 browser.on('message',(bytes,binary)=>{if(binary)return;const message=JSON.parse(bytes.toString());
  if(message.type==='warning'){report.warnings=report.warnings||[];if(report.warnings.length<8)report.warnings.push(message.message);}
  if(message.type==='visitorPersona'){report.personaCount=(report.personaCount||0)+1;report.personaFields=Object.keys(message);}
  if(message.type==='state'){connected=message.state==='connected';if(message.sessionId)session=message.sessionId;if(message.state==='error')errors.push(message.message);}
  if(message.type==='visitorPersona')persona=validateVisitorPersona(Object.fromEntries(['displayName','avatarURL','avatarScale','avatarFavorites'].filter(key=>Object.hasOwn(message,key)).map(key=>[key,message[key]])));
  if(message.type==='avatars')avatar=message.avatars.find(value=>String(value.id).replace(/[{}]/g,'').toLowerCase()===String(message.selfId).replace(/[{}]/g,'').toLowerCase());
  if(message.type==='pose'||message.type==='poseRequest'){pose={position:message.position,orientation:message.orientation};if(message.type==='poseRequest')browser.send(JSON.stringify({type:'poseAccepted',nonce:message.nonce,permissionRevision:message.permissionRevision}));}
 });await once(browser,'open');timer=setInterval(()=>{if(connected&&pose)browser.send(JSON.stringify({type:'pose',...pose}));},50);
 let previous;
 for(let iteration=0;iteration<3;iteration++){
  const chosenName=iteration===2?'Chosen visitor 世界 😀 '.repeat(10):initial.displayName;
  persona=null;avatar=null;browser.send(JSON.stringify({type:'join',domain:'overte://127.0.0.2:45102',displayName:chosenName,visitorPersona:initial}));
  await wait(()=>connected&&persona?.avatarFavorites?.length===4&&avatar?.displayName===chosenName);
  assert.deepEqual(persona.avatarFavorites,initial.avatarFavorites);assert.equal(persona.displayName,chosenName);assert.equal(persona.avatarURL.replace(/^qrc:/,'resource:'),initial.avatarURL);assert.ok(Math.abs(persona.avatarScale-initial.avatarScale)<.0001);
  assert.ok(Math.abs(avatar.scale-initial.avatarScale)<.0001);if(previous)assert.notEqual(session,previous);
  report.assertions.push(iteration===2?'The independently chosen complete Unicode join name overrides the stale persona name in actual native AvatarList and the exported visitor persona, while preserving the original avatar, scale and all four favorites':`Fresh native worker ${iteration+1} restores the complete Unicode display name, original avatar, scale 1.2 and all four actual version3 favorites including prototype-sensitive names`);
  previous=session;browser.send(JSON.stringify({type:'leave'}));await wait(()=>!connected);await new Promise(resolve=>setTimeout(resolve,3500));
 }
 assert.deepEqual(await hashes(),report.sourceSHA256);report.passed=true;
}catch(error){report.failure=error.message;report.actualConnected=connected;report.latestPersona=persona;report.actualDisplayNameMatches=avatar?.displayName===initial.displayName;report.nativeAvatarURL=avatar?.skeletonModelURL;process.exitCode=1;}
finally{
 clearInterval(timer);browser?.close(1000,'Persona proof finished');gateway.kill('SIGTERM');await once(gateway,'exit');
 report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,'visitor-persona.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});console.log(JSON.stringify(report));
}
