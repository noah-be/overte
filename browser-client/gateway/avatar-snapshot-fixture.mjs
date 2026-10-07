// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';import{readFileSync}from'node:fs';import vm from'node:vm';import{stripTypeScriptTypes}from'node:module';
import{AvatarSnapshotSender as AvatarSenderPrototype,MAX_BUFFER}from'./avatar-snapshot-sender.mjs';
const source=readFileSync(new URL('./server.mjs',import.meta.url),'utf8'),start=source.indexOf('const send = (socket, value, observe) => {'),end=source.indexOf('// Uses the already captured',start);assert(start>=0&&end>start);const c={WebSocket:{OPEN:1},JSON};vm.createContext(c);vm.runInContext(source.slice(start,end)+'\nglobalThis.oldSend=send;',c);
const session=readFileSync(new URL('../src/session.ts',import.meta.url),'utf8'),a=session.indexOf('function isRecord('),b=session.indexOf('export interface SessionCallbacks',a);assert(a>=0&&b>a);const parser={};vm.createContext(parser);vm.runInContext(stripTypeScriptTypes(session.slice(a,b).replace('export function parseServerMessage','function parseServerMessage'))+'\nglobalThis.parse=parseServerMessage;',parser);
export const parse=text=>parser.parse(text);
export const pose=position=>({type:'avatars',sessionId:'synthetic',selfId:'self',avatars:[{id:'self',position:{x:0,y:1.8,z:0}},{id:'peer',position,displayName:'fixture'}]});
export const oldSend=c.oldSend;
export function setup(){const calls=[],observed=[],socket={readyState:1,bufferedAmount:0,send(text,callback){calls.push({text,callback});}};let owner={browser:socket,native:{},permissionRevision:1,permissionsApproved:true,closed:false,isCurrent:()=>true};const sender=new AvatarSenderPrototype(socket,()=>owner,x=>observed.push(x));return{sender,socket,calls,observed,get owner(){return owner;},replace(value){owner=value;}};}
