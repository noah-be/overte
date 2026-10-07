// SPDX-License-Identifier: Apache-2.0
// Actual adapter source with controlled filesystem boundaries; no installation.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source=(await readFile(new URL('../src/trusted-network-entry.mjs',import.meta.url),'utf8'))
 .replace(/^import .*;$/gm,'').replace(/export /g,'');
function fixture({badExecutable=false,badConfig=false}={}) {
 const calls=[];let closed=0;
 const owned={fd:17,async stat(){return {isFile:()=>true,uid:1000,mode:badConfig?0o666:0o600,size:128};},async close(){closed++;}};
 const context=vm.createContext({process:{getuid:()=>1000},constants:{O_RDONLY:0,O_NOFOLLOW:131072},
   path:{dirname:p=>p.slice(0,p.lastIndexOf('/'))||'/'},
   async lstat(p){calls.push(['stat',p]);return {uid:badExecutable?1000:0,mode:p.endsWith('launcher')?0o755:0o755,isFile:()=>p.endsWith('launcher'),isDirectory:()=>!p.endsWith('launcher')};},
   async realpath(p){return p;},async open(p,flags){calls.push(['open',p,flags]);return owned;}});
 vm.runInContext(source+'\nglobalThis.entry=trustedNetworkEntry;',context);
 return {entry:context.entry,calls,get closed(){return closed;}};
}
test('fixed installed executable accepts only owned regular bounded config descriptor',async()=>{
 const f=fixture();const value=await f.entry('/tmp/overte-browser-authored/native-network.json');
 assert.equal(value.command,'/usr/libexec/overte-browser-network/launcher');
 assert.equal(value.args.length,0);assert.equal(value.options.configurationFD,17);
 assert.equal(f.calls.at(-1)[0],'open');assert.equal(f.calls.at(-1)[2],131072);
 await value.close();assert.equal(f.closed,1);
});
test('untrusted executable ancestry refuses before opening config',async()=>{
 const f=fixture({badExecutable:true});await assert.rejects(f.entry('/tmp/private'),'immutable root-owned');
 assert.equal(f.calls.some(c=>c[0]==='open'),false);assert.equal(f.closed,0);
});
test('unsafe config descriptor closes on rejection',async()=>{
 const f=fixture({badConfig:true});await assert.rejects(f.entry('/tmp/private'),'bounded owned configuration');assert.equal(f.closed,1);
});
