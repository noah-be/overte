// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {MAX_PERSONA_BYTES} from '../shared/visitor-persona.mjs';
import {VisitorPersonaStore} from './visitor-persona.ts';
const KEY='overte.browser.visitor-persona.v1';
function fixture() {
    const values=new Map<string,string>(),notices:string[]=[];
    const storage={getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);}};
    return {values,notices,storage,create:()=>new VisitorPersonaStore(storage,message=>notices.push(message))};
}
test('avatar selections, Unicode names and wearable favorites survive reload without shared mutation',()=>{
    const data=fixture(),store=data.create();
    store.update({displayName:'Überte 世界 👋',avatarURL:'https://content.overte.org/avatars/Kim.fst',avatarScale:1.5,
        avatarFavorites:[{name:'Kim',avatarURL:'https://content.overte.org/avatars/Kim.fst',avatarScale:1.5,
            avatarEntities:[{properties:{type:'Model',modelURL:'atp:/hat.fbx',localPosition:{x:0,y:1,z:0}}}]}]});
    const copy=store.snapshot();(copy.avatarFavorites![0].avatarEntities![0].properties.localPosition as {y:number}).y=900;
    assert.equal((store.snapshot().avatarFavorites![0].avatarEntities![0].properties.localPosition as {y:number}).y,1);
    assert.deepEqual(data.create().snapshot(),store.snapshot());assert.deepEqual(data.notices,[]);
});
test('partial native persona updates preserve favorites, while an explicit empty collection deletes them',()=>{
    const data=fixture(),store=data.create();
    store.update({avatarFavorites:[{name:'Default',avatarURL:'resource:/meshes/defaultAvatar_full.fst',avatarScale:1}]});
    store.update({displayName:'Updated',avatarScale:2});
    assert.equal(store.snapshot().avatarFavorites!.length,1);
    store.update({avatarFavorites:[]});assert.deepEqual(data.create().snapshot().avatarFavorites,[]);
});
test('a valid near-limit collection and valid Unicode patch cannot close the live session or destroy saved choices',()=>{
    const data=fixture(),store=data.create();
    const favorites=Array.from({length:12},(_,index)=>({name:String(index),avatarURL:'https://content.overte.org/'+'a'.repeat(4000),avatarScale:1}));
    store.update({avatarFavorites:favorites});
    const original=data.values.get(KEY)!;
    assert(new TextEncoder().encode(original).length<=MAX_PERSONA_BYTES);
    assert(MAX_PERSONA_BYTES-new TextEncoder().encode(original).length<768);
    assert.doesNotThrow(()=>store.update({displayName:'界'.repeat(256)}));
    assert.equal(data.values.get(KEY),original);assert.deepEqual(store.snapshot().avatarFavorites,favorites);
    assert.match(data.notices.at(-1)!,/world remains connected/);
});
test('foreign account fields and malformed avatar records are never copied or silently lost',()=>{
    const data=fixture(),original='{"displayName":"Saved","accountToken":"synthetic other account"}';
    data.values.set(KEY,original);data.values.set('foreign-account','synthetic foreign application');
    const store=data.create();assert.deepEqual(store.snapshot(),{});
    assert.equal(data.values.get(KEY),original);assert.equal(data.values.get(`${KEY}.recovery`),original);
    assert.throws(()=>store.update({accountToken:'never persist'} as any));
    store.update({displayName:'Visitor'});
    assert.equal(data.values.get('foreign-account'),'synthetic foreign application');
    assert.equal(data.values.get(`${KEY}.recovery`),original);
    assert(!JSON.stringify(store.snapshot()).includes('account'));
});
test('unrecoverable avatar data is preserved on quota, oversized input or an existing distinct recovery',()=>{
    for(const failure of ['quota','oversize','existing-recovery']) {
        const data=fixture(),original=failure==='oversize'?'x'.repeat(MAX_PERSONA_BYTES+1):'{invalid persona';
        data.values.set(KEY,original);
        if(failure==='existing-recovery')data.values.set(`${KEY}.recovery`,'an earlier record');
        const storage={...data.storage,setItem:(key:string,value:string)=>{
            if(failure==='quota' && key===`${KEY}.recovery`)throw Error('quota');data.storage.setItem(key,value);
        }};
        const store=new VisitorPersonaStore(storage,message=>data.notices.push(message));store.update({displayName:'In-memory visitor'});
        assert.equal(store.snapshot().displayName,'In-memory visitor');assert.equal(data.values.get(KEY),original);
        assert.match(data.notices.at(-1)!,/cannot be backed up/);
    }
});
