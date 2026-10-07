// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual native goToLocation proof against the isolated domain, never a public world.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { WebSocket } from 'ws';
import { terminateProcess } from '../../gateway/process-lifecycle.mjs';
import { createHash } from 'node:crypto';

const root = path.resolve(new URL('../../../', import.meta.url).pathname), port = 8094;
const endpoint = `http://127.0.0.1:${port}`;
const input = JSON.parse(await readFile(path.join(root, 'build/browser-hub-lab/gateway/environment-private.json'), 'utf8'));
const env = { ...(input.env || input) };
const nativeRoot = path.join(root, 'build/browser-lab/appimage/squashfs-root');
Object.assign(env, { OVERTE_GATEWAY_PORT:String(port), OVERTE_GATEWAY_HOST:'127.0.0.1',
    OVERTE_GATEWAY_ORIGINS:endpoint, OVERTE_GATEWAY_MAX_SESSIONS:'1',
    OVERTE_INTERFACE:path.join(nativeRoot,'AppRun'), OVERTE_GATEWAY_NATIVE_ROOT:nativeRoot,
    OVERTE_INTERFACE_LIBRARY_PATH:env.OVERTE_GATEWAY_PUBLIC_INTERFACE_LIBRARY_PATH,
    OVERTE_GATEWAY_DOMAINS:'overte://127.0.0.2:45102', OVERTE_GATEWAY_NATIVE_SCHEME:'hifi',
    OVERTE_GATEWAY_GUEST_POLICY:path.join(root,'build/browser-lab/config/guest-policy.json'),
    OVERTE_GATEWAY_MANAGED_UDP_PORTS:'45102,45200,45201,45202,45203,45204,45205',
    OVERTE_GATEWAY_XVFB:path.join(root,'build/browser-lab/host-tools/usr/bin/Xvfb'),
    OVERTE_GATEWAY_SLIRP:path.join(root,'build/browser-native-net/root/usr/bin/slirp4netns') });
// This transport proof does not require a Tablet UI or change installed scripts.
delete env.OVERTE_GATEWAY_DEFAULT_SCRIPTS;
const privateDirectory = path.join(root,'build/browser-lab/navigation-proof'); await mkdir(privateDirectory,{recursive:true,mode:0o700});
const privateServer = path.join(privateDirectory,'server.mjs');
let source = await readFile(path.join(root,'browser-client/gateway/server.mjs'),'utf8');
const sourceSHA256 = { 'gateway/server.mjs':createHash('sha256').update(source).digest('hex'),
    ...Object.fromEntries(await Promise.all(['native-bridge.js','native-world.js','socket-heartbeat.mjs'].map(async name => ['gateway/'+name,createHash('sha256').update(await readFile(path.join(root,'browser-client/gateway',name))).digest('hex')]))) };
source=source.replace(/from '(\.\/[^']+)'/g,(_,name)=>`from '${pathToFileURL(path.resolve(root,'browser-client/gateway',name)).href}'`)
    .replace("from 'ws'",`from '${pathToFileURL(path.join(root,'browser-client/node_modules/ws/wrapper.mjs')).href}'`)
    .replace('const directory = path.dirname(fileURLToPath(import.meta.url));',`const directory = ${JSON.stringify(path.join(root,'browser-client/gateway'))};`);
const trigger = '\nScript.setTimeout(function(){MyAvatar.goToLocation({x:5,y:1.5,z:3},false,Quat.IDENTITY,false,false);},10000);\n';
assert.ok(source.includes('const bridge = nativeBridgeSource;'), 'The private native trigger attaches only to the reviewed production bridge');
source=source.replace('const bridge = nativeBridgeSource;', `const bridge = nativeBridgeSource + ${JSON.stringify(trigger)};`);
await writeFile(privateServer,source,{mode:0o600});
const report={startedAt:new Date().toISOString(),domain:'isolated-loopback-test-domain',trigger:'actual native MyAvatar.goToLocation',
    node:process.version,sourceSHA256,publicWorldMutations:0,passed:false};
const gateway=spawn(process.execPath,[privateServer],{env,stdio:['ignore','pipe','pipe']});
let browser, movement, connected=false, request, selfId, target={position:{x:0,y:1,z:0},orientation:{x:0,y:0,z:0,w:1}};
const errors=[];
async function wait(condition,timeout=90000){const deadline=Date.now()+timeout;while(!condition()){if(errors.length)throw Error(errors[0]);if(Date.now()>deadline)throw Error('Actual native navigation proof timed out');await new Promise(resolve=>setTimeout(resolve,50));}}
try{
    gateway.stderr.on('data',()=>{});
    await Promise.race([once(gateway.stdout,'data'),once(gateway,'exit').then(()=>{throw Error('Proof gateway could not start')} )]);
    const authenticated=await fetch(endpoint+'/api/session'), cookie=authenticated.headers.get('set-cookie').split(';')[0];await authenticated.json();
    browser=new WebSocket(endpoint.replace('http:','ws:')+'/session',{headers:{Origin:endpoint,Cookie:cookie}});
    browser.on('message',(bytes,binary)=>{
        if(binary)return;const message=JSON.parse(bytes.toString());
        if(message.type==='state'){connected=message.state==='connected';if(message.selfId)selfId=message.selfId;if(message.state==='error')errors.push(message.message);}
        if(message.type==='avatars'&&message.selfId)selfId=message.selfId;
        if(message.type==='pose')target={position:message.position,orientation:message.orientation};
        if(message.type==='poseRequest'){
            if(message.position.x>4&&message.position.z>2)request=message;
            else {
                // Finish ordinary startup/spawn corrections before the test's
                // explicitly injected goToLocation target is reached.
                target={position:message.position,orientation:message.orientation};
                browser.send(JSON.stringify({type:'poseAccepted',nonce:message.nonce,permissionRevision:message.permissionRevision}));
                report.initialSpawnCorrections=(report.initialSpawnCorrections||0)+1;
            }
        }
    });
    await once(browser,'open');browser.send(JSON.stringify({type:'join',domain:'overte://127.0.0.2:45102',displayName:'Browser navigation proof'}));
    await wait(()=>connected);report.actualConnected=true;movement=setInterval(()=>browser.send(JSON.stringify({type:'pose',...target})),40);
    await wait(()=>request,25000);assert.ok(request.position.x>4 && request.position.z>2);
    report.nativeRequestedPosition=request.position;report.revision=request.permissionRevision;
    // Old browser poses continue briefly; the actual native peer must retain its teleport.
    await new Promise(resolve=>setTimeout(resolve,700));
    browser.send(JSON.stringify({type:'poseAccepted',nonce:'00000000-0000-0000-0000-000000000001',permissionRevision:request.permissionRevision}));
    await new Promise(resolve=>setTimeout(resolve,500));
    async function nativeObservation(){
        const log=await readFile(path.join(root,'build/browser-lab/logs/native.log'),'utf8');
        for(const line of log.split('\n').reverse()){
            const offset=line.indexOf('BROWSER_LAB ');if(offset<0)continue;
            try{const record=JSON.parse(line.slice(offset+'BROWSER_LAB '.length));if(record.kind==='observation')return record.data.avatars.find(avatar=>String(avatar.id).replace(/[{}]/g,'').toLowerCase()===String(selfId).replace(/[{}]/g,'').toLowerCase());}catch{/* Non-observation diagnostics are not evidence. */}
        }
    }
    let observation;const deadline=Date.now()+6000;
    while(Date.now()<deadline){observation=await nativeObservation();if(observation&&Math.abs(observation.position.x-request.position.x)<.15)break;await new Promise(resolve=>setTimeout(resolve,200));}
    assert.ok(observation&&Math.abs(observation.position.x-request.position.x)<.15,'Independent real native client retains teleport despite stale browser poses and wrong ACK');
    report.nativePeerRetainedTeleport=true;
    target={position:request.position,orientation:request.orientation};browser.send(JSON.stringify({type:'poseAccepted',nonce:request.nonce,permissionRevision:request.permissionRevision}));
    target={...target,position:{...target.position,x:target.position.x+1}};
    const movedDeadline=Date.now()+6000;
    while(Date.now()<movedDeadline){observation=await nativeObservation();if(observation&&Math.abs(observation.position.x-target.position.x)<.15)break;await new Promise(resolve=>setTimeout(resolve,200));}
    assert.ok(observation&&Math.abs(observation.position.x-target.position.x)<.15,'Browser movement resumes after exact navigation ACK');
    report.nativePeerObservedResumedMovement=true;report.passed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally{
    clearInterval(movement);if(browser?.readyState===WebSocket.OPEN)browser.send(JSON.stringify({type:'leave'}));
    browser?.close();await terminateProcess(gateway,15000);await rm(privateServer,{force:true});
    report.finishedAt=new Date().toISOString();await writeFile(path.join(privateDirectory,'result.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
