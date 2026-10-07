// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {validateVisitorPersona,personaAssetURL} from '../shared/visitor-persona.mjs';
import {approvedVisitorPersona,nativeAvatarBookmarks,prepareVisitorPersona,acceptedNativePersona} from './visitor-persona.mjs';
const origins=new Set(['https://avatars.example.test']);
const favorite={name:'世界 👋',avatarURL:'https://avatars.example.test/avatar.fst?v=2',avatarScale:.005,avatarIcon:'',avatarEntities:[{properties:{type:'Model',name:'Hat',modelURL:'atp:/hat.fbx',localPosition:{x:0,y:.2,z:0},localRotation:{x:0,y:0,z:0,w:1},parentJointIndex:2,visible:true,userData:'{"grabbableKey":{"grabbable":true}}'}}]};
test('persona preserves full Unicode names, actual scale bounds, safe wearable values and fixed native default aliases as plain clones',()=>{
 const original={displayName:'界'.repeat(256),avatarURL:'qrc:////meshes/defaultAvatar_full.fst',avatarScale:1000,avatarFavorites:[structuredClone(favorite)]};
 const clean=approvedVisitorPersona(original,origins);assert.equal(clean.avatarURL,'qrc:/meshes/defaultAvatar_full.fst');assert.equal(clean.displayName.length,256);
 original.avatarFavorites[0].avatarEntities[0].properties.name='changed';assert.equal(clean.avatarFavorites[0].avatarEntities[0].properties.name,'Hat');
 const native=nativeAvatarBookmarks(clean);assert.equal(native['世界 👋'].version,3);assert.equal(native['世界 👋'].avatarEntites[0].properties.modelURL,'atp:/hat.fbx');assert.equal(native['世界 👋'].avatarEntities,undefined);
});
test('persona rejects arbitrary host files, account metadata, scripts, credential URLs, unapproved origins and bounded collection abuse',()=>{
 for(const url of ['file:///home/operator/private.fst','qrc:/private/file','resource:/meshes/../private','https://user:pass@avatars.example.test/a','atp:/../private','atp:/a%2fb','atp:/bad%'])assert.throws(()=>personaAssetURL(url));
 for(const value of [{accountToken:'secret'},{displayName:'x'.repeat(257)},{displayName:'a\0b'},{avatarScale:.004},{avatarFavorites:Array.from({length:101},()=>favorite)},
  {avatarFavorites:[favorite,{...favorite,name:' 世界 👋 '}]},{avatarFavorites:[{...favorite,avatarEntities:[{properties:{type:'Model',script:'file:///private'}}]}]},
  {avatarFavorites:Array.from({length:100},(_,i)=>({...favorite,name:String(i),avatarURL:'https://avatars.example.test/'+ 'a'.repeat(1000)}))}])assert.throws(()=>validateVisitorPersona(value));
 assert.throws(()=>approvedVisitorPersona({avatarURL:'https://unapproved.example/avatar.fst'},origins));
 assert.deepEqual(acceptedNativePersona({displayName:'Visitor',avatarFavorites:[{...favorite,avatarURL:'https://unapproved.example/a'}]},origins).persona,{displayName:'Visitor'});
 assert.deepEqual(validateVisitorPersona({avatarFavorites:[]}),{avatarFavorites:[]},'An explicit empty collection deletes saved favorites');
});
test('fresh worker file contains only validated native version3 favorites, never Qt accounts or old session IDs',async t=>{
 const directory=await mkdtemp(path.join(tmpdir(),'persona-test-'));t.after(()=>rm(directory,{recursive:true,force:true}));
 await prepareVisitorPersona(directory,{avatarFavorites:[favorite]},origins,'Overte - Dev');
 const file=JSON.parse(await readFile(path.join(directory,'data/Overte - Dev/Interface/avatarbookmarks.json'),'utf8'));
 assert.deepEqual(file,JSON.parse(JSON.stringify(nativeAvatarBookmarks({avatarFavorites:[favorite]}))));assert.equal(file['世界 👋'].avatarEntites[0].properties.parentID,undefined);
 await assert.rejects(prepareVisitorPersona(directory,{},origins,'../../operator'));
});
const source=await readFile(new URL('./native-visitor-persona.js',import.meta.url),'utf8');
test('native persona restores only after admission, waits for selected model and exports ordinary user changes under the current revision',()=>{
 let authority=null,now=0;const messages=[],calls=[],avatar={displayName:'default',skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst',scale:1,
  useFullAvatarURL(url){calls.push(['model',url]);},setAvatarScale(scale){this.scale=scale;calls.push(['scale',scale]);},getTargetScale(){return this.scale;}};
 const factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPersona;',{Date:{now:()=>now}});
 const worker=factory({initial:{displayName:'世界',avatarURL:favorite.avatarURL,avatarScale:.5},avatar,bookmarks:{getBookmarks:()=>({})},
  wearableFields:[],runtimeFields:[],inertFields:{},revision:()=>7,authority:()=>authority,send:m=>messages.push(JSON.parse(JSON.stringify(m)))});
 worker.restore();worker.poll(true);assert.deepEqual(calls,[]);authority='7|approved';worker.restore();worker.poll(true);
 assert.equal(avatar.displayName,'世界');assert.equal(messages.at(-1).avatarURL,undefined,'A loading model does not replace the saved selection with the old default');
 avatar.skeletonModelURL=favorite.avatarURL;now=1000;worker.poll();assert.equal(messages.at(-1).avatarURL,favorite.avatarURL);assert.equal(messages.at(-1).avatarScale,.5);
 avatar.displayName='Changed';now=2000;worker.poll();assert.equal(messages.at(-1).displayName,'Changed');assert.equal(messages.at(-1).permissionRevision,7);
 authority=null;avatar.displayName='revoked';worker.poll(true);assert.equal(messages.at(-1).displayName,'Changed');worker.stop();authority='8|new';worker.poll(true);assert.equal(messages.at(-1).displayName,'Changed');
});
test('a visitor join name takes precedence over a stale bounded persona record after native approval',()=>{
 const factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPersona;');let authority=null;
 const avatar={displayName:'default',skeletonModelURL:'qrc:/meshes/defaultAvatar_full.fst',getTargetScale:()=>1};
 const worker=factory({initial:{displayName:'Previously saved'},displayName:'界'.repeat(256),avatar,bookmarks:{getBookmarks:()=>({})},
  wearableFields:[],runtimeFields:[],inertFields:{},revision:()=>1,authority:()=>authority,send:()=>{}});
 worker.restore();assert.equal(avatar.displayName,'default');
 authority='approved';worker.restore();assert.equal(avatar.displayName,'界'.repeat(256));worker.stop();
});
test('unsupported native wearables and rejected initial origins preserve saved favorites until an explicit native change',()=>{
 const factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPersona;');let raw={Favorite:{version:3,avatarUrl:favorite.avatarURL,avatarScale:1,avatarEntites:[{properties:{type:'Model',script:'unsafe'}}]}},messages=[];
 const avatar={displayName:'Visitor',skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst',getTargetScale:()=>1};
 const worker=factory({initial:{},preserveFields:['avatarURL','avatarFavorites'],avatar,bookmarks:{getBookmarks:()=>raw},wearableFields:['type'],runtimeFields:[],inertFields:{script:''},revision:()=>1,authority:()=> 'approved',send:m=>messages.push(JSON.parse(JSON.stringify(m)))});
 worker.restore();worker.poll(true);assert.equal(messages.at(-1).avatarFavorites,undefined);assert.equal(messages.at(-1).avatarURL,undefined);
 assert.equal(messages.filter(m=>m.type==='warning').length,1);raw={};avatar.skeletonModelURL=favorite.avatarURL;worker.poll(true);
 assert.deepEqual(messages.at(-1).avatarFavorites,[]);assert.equal(messages.at(-1).avatarURL,favorite.avatarURL);
});


test('prototype-sensitive favorite names survive private serialization and native API export without prototype mutation',()=>{
 const names=['__proto__','constructor','toString'];
 const records=nativeAvatarBookmarks({avatarFavorites:names.map(name=>({...favorite,name,avatarEntities:[]}))});
 assert.equal(Object.getPrototypeOf(records),null);const raw=JSON.parse(JSON.stringify(records));
 for(const name of names)assert.equal(Object.hasOwn(raw,name),true);
 const messages=[],factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPersona;');
 const worker=factory({initial:{},avatar:{displayName:'Visitor',skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst',getTargetScale:()=>1},
  bookmarks:{getBookmarks:()=>raw},wearableFields:[],runtimeFields:[],inertFields:{},revision:()=>1,authority:()=> 'approved',send:m=>messages.push(JSON.parse(JSON.stringify(m)))});
 worker.restore();worker.poll(true);assert.deepEqual(messages.at(-1).avatarFavorites.map(f=>f.name).sort(),names.sort());
});


test('documented single-bookmark lookup recovers the real native QVariant map __proto__ conversion loss',()=>{
 const record={version:3,avatarUrl:favorite.avatarURL,avatarScale:1,avatarIcon:'',avatarEntites:[]};
 const broken={};broken.__proto__=record;broken.constructor=record;broken.toString=record;
 assert.equal(Object.keys(broken).includes('__proto__'),false,'Emulate actual native setProperty conversion');
 const messages=[],factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPersona;');
 const worker=factory({initial:{},avatar:{displayName:'Visitor',skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst',getTargetScale:()=>1},bookmarks:{getBookmarks:()=>broken,getBookmark:name=>name==='__proto__'?record:{}},
  wearableFields:[],runtimeFields:[],inertFields:{},revision:()=>1,authority:()=> 'approved',send:m=>messages.push(JSON.parse(JSON.stringify(m)))});
 worker.restore();worker.poll(true);assert.deepEqual(messages.at(-1).avatarFavorites.map(f=>f.name).sort(),['__proto__','constructor','toString']);
});
