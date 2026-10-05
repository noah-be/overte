// SPDX-License-Identifier: Apache-2.0
// Actual complete launch/native-handler/browser methods; only external IO and
// process creation are controlled. No native, audio, sockets or real timers.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import path from 'node:path';
import {readFileSync} from 'node:fs';
import {EventEmitter} from 'node:events';
import {stripTypeScriptTypes} from 'node:module';
import {AvatarSnapshotSender} from './avatar-snapshot-sender.mjs';
import {SharedTeardown} from './process-lifecycle.mjs';
import {PushToTalkSession} from './push-to-talk.mjs';
import {domainAddress,managedUDPDomain,validateNativePermissions} from './validation.mjs';
import {validatePermissionPolicy,PERMISSION_KEYS} from './permission-policy.mjs';
import {managedNavigationSelection} from './navigation.mjs';
import {acceptedNativePersona} from './visitor-persona.mjs';
import {validateVisitorPreferences} from '../shared/visitor-preferences.mjs';
import {validateVisitorPersona,WEARABLE_FIELDS} from '../shared/visitor-persona.mjs';

const source=readFileSync(new URL('./server.mjs',import.meta.url),'utf8');
function uniqueSlice(start,end){assert.equal(source.split(start).length,2);assert.equal(source.split(end).length,2);return source.slice(source.indexOf(start),source.indexOf(end));}
const launchClass=uniqueSlice('class Session extends SharedTeardown {','const server = http.createServer');
const nativeHandler=uniqueSlice("nativeServer.on('connection',",'const heartbeat = setInterval');
const sendHelpers=uniqueSlice('const send = (socket, value, observe) => {','const cookie = request =>');
const nativeDomain='overte://127.0.0.2:40102';
const permissions=Object.fromEntries(PERMISSION_KEYS.map(key=>[key,['id_can_connect','id_can_view_asset_urls'].includes(key)]));
const policy=validatePermissionPolicy({domain:nativeDomain,settings:{version:2.7,security:{standard_permissions:['anonymous','localhost'].map(permissions_id=>({permissions_id,...permissions}))}}});
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return{promise,resolve};}
function child(){const value=new EventEmitter();value.stdout=new EventEmitter();value.stderr=new EventEmitter();value.stdin=new EventEmitter();value.exitCode=null;return value;}
function client(){
    const errors=[],states=[],acks=[],world={poses:[],clears:0,setLocalAvatar(){},setAvatars(value){this.poses=value;},setEntities(){this.clears++;},setEnabled(){},invalidateSourceTexts(){},invalidateModelParses(){}};
    let onAck;
    class Socket{static OPEN=1;readyState=1;sent=[];closeCalls=[];send(text){const value=JSON.parse(text);this.sent.push(value);if(value.type==='avatarConsumed'){acks.push(value);onAck?.(value);}}close(...args){this.closeCalls.push(args);this.readyState=3;}receive(text){this.onmessage({data:text});}}
    const elements=new Map(),c={WebSocket:Socket,window:{location:{href:'http://owned.invalid'}},URL,TextEncoder,ArrayBuffer,performance:{now:()=>0},setTimeout:()=>1,clearTimeout(){},DOMException,
        ready:false,world,worldLoaded:true,entityCount:1,avatarCount:0,joining:true,permissionRevision:0,navigationAttempt:undefined,navigationHistory:{commit(){}},
        pushToTalk:undefined,graphicsIntent:undefined,graphicsScan:undefined,graphics:undefined,browserCapture:undefined,tablet:undefined,audio:undefined,tabletButton:{disabled:true},
        showState(){},log(){},updateStats(){},updateMicrophone(){},sendNavigationHistory(){},reset(){},element(id){if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
    vm.createContext(c);
    for(const name of ['session.ts','compressed-color-session.ts']){const text=readFileSync(new URL('../src/'+name,import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace(/^export /gm,'');vm.runInContext(stripTypeScriptTypes(text,{mode:'transform'}),c);}
    const main=readFileSync(new URL('../src/main.ts',import.meta.url),'utf8'),a=main.indexOf('function onMessage('),b=main.indexOf('\nconst session =',a);assert(a>=0&&b>a);
    vm.runInContext(stripTypeScriptTypes(main.slice(a,b),{mode:'transform'})+'\nglobalThis.apply=onMessage;globalThis.Client=CompressedColorSession;',c);
    const session=new c.Client({message:value=>{if(value.type==='state')states.push({...value});return c.apply(value);},audio(){},closed(){},error:value=>errors.push(value)});c.session=session;
    session.join(nativeDomain,'Browser visitor');const socket=session.socket;socket.onopen();
    return{session,socket,errors,states,acks,world,context:c,setAck(fn){onAck=fn;}};
}
function setup({legacy=false,worker=true}={}){
    const peer=client(),entered=deferred(),release=deferred(),writes=[],calls=[],sessions=new Map();let owner,connect;
    const browser={readyState:1,bufferedAmount:0,send(text,callback){const value=JSON.parse(text);calls.push({kind:'browser-write',state:value.state});writes.push(value);peer.socket.receive(text);callback?.();},close(){}};
    const c={SharedTeardown,PushToTalkSession,AvatarSnapshotSender,domainAddress,managedNavigationSelection,managedUDPDomain,validateNativePermissions,validateVisitorPreferences,validateVisitorPersona,WEARABLE_FIELDS,acceptedNativePersona,
        randomUUID:()=> 'owned',randomBytes:()=>({toString:()=> 'token'}),domains:[nativeDomain],publicPlaces:[],assetOrigins:new Set(),publicAssetOrigins:new Set(),path,port:8090,nativeBridgeSource:'/* controlled source text */',
        process:{env:{OVERTE_INTERFACE:'/owned/interface',OVERTE_GATEWAY_GUEST_POLICY:'/owned/policy.json',OVERTE_GATEWAY_MANAGED_UDP_PORTS:'40102',...(worker?{}:{OVERTE_GATEWAY_WORKER_ISOLATION:'off'})}},
        readPolicyFile:async()=>new Map([[nativeDomain,policy]]),nativeDomainAddress:async value=>value,mkdtemp:async()=>'/owned/session',tmpdir:()=>'/owned',mkdir:async()=>{},writeFile:async()=>{},run:async()=>{},
        prepareVisitorPersona:async()=>({}),prepareWorker:async()=>({command:'/owned/worker',args:[],env:{}}),AbortController,
        launchNativeNetwork:async options=>{calls.push({kind:'launch',options});entered.resolve();await release.promise;return{child:child()};},
        setTimeout:()=>1,clearTimeout(){},WebSocket:{OPEN:1},Buffer,JSON,Date,sessions,sockets:new Set(),equal:(a,b)=>a===b,NativeHeartbeat:class{receive(){}},nativeServer:{on(_,fn){connect=fn;}}};
    vm.createContext(c);vm.runInContext(sendHelpers+launchClass+'\nglobalThis.Session=Session;'+nativeHandler,c);
    const sender=new AvatarSnapshotSender(browser,()=>owner);owner=new c.Session(browser,'owner',()=>true,sender);owner.avatarConsumption=legacy?'legacy':'ack-v1';
    owner.process=(command,args,env,label)=>{calls.push({kind:'process',label});return child();};sessions.set(owner.id,owner);
    peer.setAck(value=>sender.acknowledge(owner,value));
    const handlers={},native={readyState:1,bufferedAmount:0,on(name,fn){handlers[name]=fn;},send(){},close(){calls.push({kind:'native-close'});}};connect(native);
    const receive=value=>handlers.message(Buffer.from(JSON.stringify(value)));
    const launch=()=>owner.launch({domain:nativeDomain,displayName:'Browser visitor'});
    const approve=async()=>{await receive({type:'nativeHello',token:owner.token});await receive({type:'permissions',domain:nativeDomain,permissionRevision:1,permissions});};
    const connected=()=>receive({type:'state',state:'connected'});
    const avatars=()=>receive({type:'avatars',avatars:[{id:'peer',position:{x:4,y:1.8,z:2}}]});
    return{owner,sender,peer,entered,release,writes,calls,launch,approve,connected,avatars,receive};
}

test('complete worker launch announces startup before native relay can publish authority',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;try{assert.equal(x.writes.length,1);assert.equal(x.writes[0].state,'connecting');assert.equal(x.writes[0].avatarEpoch,0);assert.equal(x.writes[0].permissionRevision,undefined);}finally{x.release.resolve();await promise;}assert.equal(x.writes.filter(value=>value.state==='connecting').length,1);});
test('early native approval and connection remain valid when complete launch resumes',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;await x.approve();await x.connected();assert.equal(x.peer.session.connected,true);assert(x.peer.session.compressedAssetApproval);x.release.resolve();await promise;assert.equal(x.peer.session.connected,true);assert.equal(x.peer.context.ready,true);assert(x.peer.session.compressedAssetApproval);await x.avatars();assert.equal(x.peer.errors.length,0);assert.equal(x.peer.acks.length,1);assert.equal(x.peer.world.poses.length,1);assert.equal(x.peer.world.clears,0);});
test('early approved-before-connected consumed epoch is not followed by stale startup',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;await x.approve();await x.avatars();assert.equal(x.peer.acks.length,1);assert.equal(x.peer.session.connected,false);x.release.resolve();await promise;await x.avatars();assert.equal(x.peer.errors.length,0);assert.equal(x.peer.socket.closeCalls.length,0);assert.equal(x.peer.acks.length,2);});
test('early connected consumed epoch survives resumed full launch without protocol close',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;await x.approve();await x.connected();await x.avatars();assert.equal(x.peer.acks.length,1);x.release.resolve();await promise;await x.avatars();assert.equal(x.peer.errors.length,0);assert.equal(x.peer.socket.closeCalls.length,0);assert.equal(x.peer.acks.length,2);assert.equal(x.peer.session.connected,true);});
test('ordinary post-launch native events still grant and consume complete snapshots',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;x.release.resolve();await promise;await x.approve();await x.connected();await x.avatars();assert.equal(x.peer.errors.length,0);assert.equal(x.peer.acks.length,1);assert.equal(x.peer.session.connected,true);});
test('genuine worker reconnect still revokes prior epoch and reapproves early snapshots',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;x.release.resolve();await promise;await x.approve();await x.connected();await x.avatars();const epoch=x.sender.epoch;await x.receive({type:'state',state:'connecting'});assert.equal(x.sender.epoch,epoch+1);assert.equal(x.peer.session.connected,false);assert.equal(x.peer.session.compressedAssetApproval,undefined);await x.receive({type:'permissions',domain:nativeDomain,permissionRevision:1,permissions});await x.avatars();assert.equal(x.peer.acks.length,2);assert.equal(x.peer.errors.length,0);assert.equal(x.peer.session.connected,false);});
test('explicit legacy startup retains absent delivery metadata and ordinary consumption',async()=>{const x=setup({legacy:true});const promise=x.launch();await x.entered.promise;x.release.resolve();await promise;await x.approve();await x.connected();await x.avatars();assert.equal(x.writes[0].avatarConsumption,undefined);assert.equal(x.writes[0].avatarEpoch,undefined);assert.equal(x.peer.acks.length,0);assert.equal(x.peer.errors.length,0);assert.equal(x.peer.world.poses.length,1);});
test('nonworker launch announces once before native process creation and preserves grants',async()=>{const x=setup({worker:false});await x.launch();assert.equal(x.writes[0].state,'connecting');assert.equal(x.writes.filter(value=>value.state==='connecting').length,1);await x.approve();await x.connected();await x.avatars();assert.equal(x.peer.acks.length,1);assert.equal(x.peer.errors.length,0);});
test('revocation while network setup is pending refuses launch continuation and fresh writes',async()=>{const x=setup();const promise=x.launch();await x.entered.promise;x.owner.revoke();x.release.resolve();await assert.rejects(promise,/Session cancelled/);const count=x.writes.length;await x.receive({type:'nativeHello',token:x.owner.token});assert.equal(x.writes.length,count);assert.equal(x.sender.pending,null);assert.equal(x.sender.consumption,null);});
