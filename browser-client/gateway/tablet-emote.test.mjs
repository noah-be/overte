// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {readFile,mkdtemp,mkdir,writeFile,rm,stat,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {buildBrowserEmoteOverride,loadBrowserEmotePackage,EMOTE_SOURCE_SHA256} from './tablet-emote.mjs';
import {sandboxCommand} from './worker-sandbox.mjs';
const original=gunzipSync(await readFile(new URL('./fixtures/native-emote-f91d15a.js.gz',import.meta.url)),{maxOutputLength:32768}).toString('utf8');
const signal=()=>({callbacks:new Set(),connect(f){this.callbacks.add(f);},disconnect(f){this.callbacks.delete(f);},emit(...args){for(const f of [...this.callbacks])f(...args);}});
function run(source,{state=3,frames=120,random=0}={}){
 const web=signal(),key=signal(),ending=signal(),calls=[],timers=[],cleared=[],animations=new Map();let frameReads=0;
 const animation=name=>{if(!animations.has(name))animations.set(name,{resource:{state},animation:{get frames(){frameReads++;return typeof frames==='function'?frames(name):frames===null?null:{length:frames};}}});return animations.get(name);};
 const mapping={from(){return {peek(){return {to(){}};}};}};
 vm.runInNewContext(source,{Script:{resolvePath:value=>'/native/'+value,setTimeout(fn,ms){timers.push({fn,ms});return timers.length;},clearTimeout:id=>cleared.push(id),scriptEnding:ending},Tablet:{getTablet(){return {webEventReceived:web,screenChanged:signal(),addButton(){return {clicked:signal(),editProperties(){}};},gotoHomeScreen(){},gotoWebScreen(){},removeButton(){}};}},Controller:{Standard:{},newMapping(){return mapping;},keyPressEvent:key,enableMapping(){},disableMapping(){}},AnimationCache:{prefetch(url){return animation(path.basename(url,'.fbx')).resource;},getAnimation(url){return animation(path.basename(url,'.fbx')).animation;}},MyAvatar:{overrideAnimation(...args){calls.push(args);},restoreAnimation(){calls.push('restore');}},Math:Object.assign(Object.create(Math),{random:()=>random})});
 return {click:name=>web.emit({type:'click',data:name}),key,ending,calls,timers,cleared,animations,frameReads:()=>frameReads};
}
test('actual pinned packaged Sit passes undefined endFrame; corrected original handler passes real native frame count',()=>{
 assert.equal(createHash('sha256').update(original).digest('hex'),EMOTE_SOURCE_SHA256);const old=run(original),fixed=run(buildBrowserEmoteOverride(original));old.click('Sit');fixed.click('Sit');assert.equal(old.calls[0][4],undefined);assert.equal(fixed.calls[0][4],120);assert.deepEqual(fixed.calls[0].slice(1,4),[60,false,0]);assert.equal(fixed.timers.length,0);assert.equal(fixed.frameReads(),1);
});
test('all three actual native Sit variants use their own frames without creating a completion timer',()=>{
 for(let index=1;index<=3;index++){const source=buildBrowserEmoteOverride(original);const f=run(source,{random:(index-.5)/3,frames:name=>({length:name===`Sit${index}`?50+index:120})});
 f.click('Sit');assert.equal(f.calls[0][4],50+index);assert.equal(f.timers.length,0);}
});
test('non-Sit original arguments and timer duration/restore are preserved; real second click still stops',()=>{
 for(const source of [original,buildBrowserEmoteOverride(original)]){const f=run(source);f.click('Waving');assert.equal(f.calls[0][4],120);assert.equal(f.timers[0].ms,2000);f.click('Waving');assert.equal(f.calls[1],'restore');assert.deepEqual(f.cleared,[1]);}
 const f=run(buildBrowserEmoteOverride(original));f.click('Waving');f.timers[0].fn();assert.equal(f.calls[1],'restore');
});
test('same Sit click and genuine native key restore avoid unnecessary frame getter and preserve original connections',()=>{
 const f=run(buildBrowserEmoteOverride(original));f.click('Sit');const reads=f.frameReads();f.click('Sit');assert.equal(f.calls[1],'restore');assert.equal(f.frameReads(),reads);f.click('Sit');f.key.emit();assert.equal(f.calls.at(-1),'restore');assert.equal(f.key.callbacks.size,0);
});
test('unready native resource never reads frames or changes animation state',()=>{
 const f=run(buildBrowserEmoteOverride(original),{state:2,frames:()=>{throw Error('Must not read unready frames');}});f.click('Sit');f.click('Waving');assert.equal(f.calls.length,0);assert.equal(f.frameReads(),0);
});
test('missing/empty/invalid ready frame data refuses a new animation before cancelling existing native playback',()=>{
 for(const value of [null,undefined,0,-1,NaN,Infinity,1.5,9007199254740992]){const f=run(buildBrowserEmoteOverride(original),{frames:name=>name==='Waving'?{length:120}:value===null?null:{length:value}});f.click('Waving');f.click('Sit');assert.equal(f.calls.length,1);assert.equal(f.cleared.length,0);f.click('Waving');assert.equal(f.calls.at(-1),'restore');}
});
test('original script cleanup remains connected and cancels its non-Sit native timer',()=>{
 const f=run(buildBrowserEmoteOverride(original));f.click('Waving');f.ending.emit();assert.deepEqual(f.cleared,[1]);assert.equal(f.calls.at(-1),'restore');
});
test('unknown source hash refuses rather than applying the textual replacement to a different native version',()=>{
 for(const source of ['',original+'\n',original.replace('var FPS = 60;','var FPS = 30;')])assert.throws(()=>buildBrowserEmoteOverride(source),/Unsupported installed Emote source/);
});
async function packageFixture(){const directory=await mkdtemp(path.join(tmpdir(),'overte-emote-test-')),root=path.join(directory,'installed'),scripts=path.join(root,'scripts');await mkdir(path.join(scripts,'system'),{recursive:true});const defaults=path.join(scripts,'defaultScripts.js'),target=path.join(scripts,'system/emote.js');await writeFile(defaults,'// trusted installed defaults');await writeFile(target,original);return {directory,root,defaults,target};}
test('startup-cached exact source creates distinct private wx adapters, preserves installed bytes and refuses unknown targets',async()=>{
 const f=await packageFixture();try{const pack=await loadBrowserEmotePackage(pathToFileURL(f.defaults).href);await writeFile(f.target,'changed after validated startup');const first=path.join(f.directory,'one'),second=path.join(f.directory,'two');await mkdir(first);await mkdir(second);const a=await pack.prepare(first),b=await pack.prepare(second);assert.notEqual(a.readOnlyOverrides[0].source,b.readOnlyOverrides[0].source);assert.equal(await readFile(a.readOnlyOverrides[0].source,'utf8'),buildBrowserEmoteOverride(original));assert.equal((await stat(a.readOnlyOverrides[0].source)).mode&0o777,0o600);assert.equal(await readFile(f.target,'utf8'),'changed after validated startup');await assert.rejects(pack.prepare(first),{code:'EEXIST'});await assert.rejects(loadBrowserEmotePackage(pathToFileURL(f.defaults).href),/Unsupported installed Emote source/);for(const url of ['https://example.invalid/defaultScripts.js',pathToFileURL(f.defaults).href+'?override=1',pathToFileURL(f.target).href])await assert.rejects(loadBrowserEmotePackage(url),/Unsupported installed Emote path/);}finally{await rm(f.directory,{recursive:true,force:true});}
});
test('actual sandbox binding admits only exact owned canonical Emote adapter and installed target, preserving originals',async()=>{
 const f=await packageFixture();try{const profile=path.join(f.directory,'profile'),sibling=path.join(f.directory,'sibling');await mkdir(profile);await mkdir(sibling);const pack=await loadBrowserEmotePackage(pathToFileURL(f.defaults).href),prepared=await pack.prepare(profile),override=prepared.readOnlyOverrides[0],options={directory:profile,executable:process.execPath,env:{},roots:[f.root]};const launch=await sandboxCommand({...options,readOnlyOverrides:prepared.readOnlyOverrides});const at=launch.args.indexOf(override.source);assert.equal(launch.args[at-1],'--ro-bind');assert.equal(launch.args[at+1],f.target);assert.equal(await readFile(f.target,'utf8'),original);
 const other=path.join(sibling,'browser-emote.js');await writeFile(other,'sibling');await assert.rejects(sandboxCommand({...options,readOnlyOverrides:[{source:other,target:f.target}]}),/Only reviewed session/);await assert.rejects(sandboxCommand({...options,readOnlyOverrides:[{source:override.source,target:f.defaults}]}),/Only reviewed session/);await assert.rejects(sandboxCommand({...options,readOnlyOverrides:[{source:override.source,target:'/etc/passwd'}]}),/Only reviewed session/);
 const alias=path.join(f.directory,'alias');await symlink(profile,alias);await assert.rejects(sandboxCommand({...options,directory:alias,readOnlyOverrides:[{source:path.join(alias,'browser-emote.js'),target:f.target}]}),/canonical owned/);await rm(override.source);await symlink(f.target,override.source);await assert.rejects(sandboxCommand({...options,readOnlyOverrides:prepared.readOnlyOverrides}),/regular trusted script/);
 }finally{await rm(f.directory,{recursive:true,force:true});}
});
