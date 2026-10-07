// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {validateVisitorPreferences,visitorAddress} from '../shared/visitor-preferences.mjs';

test('visitor preferences contain only canonical plain bookmark and home clones',()=>{
    const original={bookmarks:[{name:'  世界 👋  ',address:'hifi://overte_hub/1,2,3/0,0,0,1'}],home:'overte_hub'};
    const clean=validateVisitorPreferences(original);
    assert.deepEqual(clean,{bookmarks:[{name:'世界 👋',address:'overte://overte_hub/1,2,3/0,0,0,1'}],home:'overte://overte_hub'});
    original.bookmarks[0].name='changed';assert.equal(clean.bookmarks[0].name,'世界 👋');
    assert.deepEqual(validateVisitorPreferences({bookmarks:[{name:'Home',address:'my_home'}]}),{bookmarks:[],home:'overte://my_home'});
    assert.equal(visitorAddress('safe_unlisted_world'), 'overte://safe_unlisted_world','Saving is not admission: safe unsupported destinations remain bookmarks');
});
test('bookmark schema refuses credentials, file paths, account metadata, duplicate names and malformed viewpoints',()=>{
    for(const address of ['file:///operator/home','http://host','atp:/asset','overte://name@host','hifi://user:secret@host',
        'overte://world?token=secret','overte://world#secret','overte://world/NaN,2,3','overte://world/1e99,2,3','overte://world/1,2,3/0,0,0,0','overte://world:99999','overte://wo\nrld'])assert.throws(()=>visitorAddress(address));
    for(const value of [null,[],{bookmarks:[],accountToken:'secret'},{bookmarks:[{name:'',address:'world'}]},
        {bookmarks:[{name:'A\0B',address:'world'}]},{bookmarks:[{name:'x'.repeat(65),address:'world'}]},
        {bookmarks:[{name:'x',address:'world',file:'/operator/home'}]},
        {bookmarks:[{name:'same',address:'one'},{name:' same ',address:'two'}]},
        {bookmarks:Array.from({length:101},(_,i)=>({name:String(i),address:'world'}))}])assert.throws(()=>validateVisitorPreferences(value));
    assert.equal(validateVisitorPreferences({bookmarks:Array.from({length:100},(_,i)=>({name:String(i),address:'world'}))}).bookmarks.length,100);
});

const source=await readFile(new URL('./native-visitor-preferences.js',import.meta.url),'utf8');
test('fresh visitor preferences remove old private bookmarks without creating an empty native Home card',()=>{
    const data={Home:'hifi://old_private_home',Old:'hifi://old_private_bookmark'},messages=[];
    const factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPreferences;');
    const api={getBookmarks:()=>data,getHomeLocationAddress:()=>data.Home||'',
        removeBookmark(name){delete data[name];},addBookmark(name,address){data[name]=address;},
        setHomeLocationToAddress(address){data.Home=address;}};
    const worker=factory({initial:{bookmarks:[]},api,authority:()=> '1|approved',revision:()=>1,send:message=>messages.push(JSON.parse(JSON.stringify(message)))});
    worker.restore();worker.poll(true);
    assert.deepEqual(data,{},'The actual native bookmark API contains no ghost Home entry');
    assert.deepEqual(messages,[{type:'visitorPreferences',permissionRevision:1,bookmarks:[]}]);
});
test('native restoration touches only approved private bookmark APIs, and changes survive a fresh worker without profile copying',()=>{
    let authority=null,now=0;const messages=[],calls=[];let data={};
    const factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPreferences;',{Date:{now:()=>now}});
    const api={getBookmarks:()=>data,getHomeLocationAddress:()=>data.Home||'',
        removeBookmark(name){calls.push(['remove',name]);delete data[name];},
        addBookmark(name,address){calls.push(['add',name,address]);data[name]=address;},
        setHomeLocationToAddress(address){calls.push(['home',address]);data.Home=address;}};
    const initial=validateVisitorPreferences({bookmarks:[{name:'Mine',address:'world/5,1.5,3'}],home:'home_world'});
    const worker=factory({initial,api,authority:()=>authority,revision:()=>7,send:message=>messages.push(JSON.parse(JSON.stringify(message)))});
    worker.restore();worker.poll(true);assert.deepEqual(calls,[]);assert.deepEqual(messages,[]);
    authority='7|world';worker.restore();worker.poll(true);
    assert.deepEqual(calls,[['add','Mine','hifi://world/5,1.5,3'],['home','hifi://home_world']]);
    let saved=validateVisitorPreferences({bookmarks:messages[0].bookmarks,home:messages[0].home});
    assert.deepEqual(saved,initial);
    data.Other='overte://unsupported_but_safe';worker.poll(true);
    saved=validateVisitorPreferences({bookmarks:messages.at(-1).bookmarks,home:messages.at(-1).home});
    assert.equal(saved.bookmarks.length,2);assert.equal(messages.at(-1).permissionRevision,7);
    worker.stop();data.Late='overte://late';const count=messages.length;worker.poll(true);assert.equal(messages.length,count);
    data={};const next=factory({initial:saved,api,authority:()=>authority,revision:()=>1,send:()=>{}});next.restore();
    assert.equal(data.Other,'hifi://unsupported_but_safe');assert.equal(data.Home,'hifi://home_world');
});
test('native preference polling is bounded, deduplicated and cannot export after authority revocation',()=>{
    let authority='approved',now=1000;const messages=[],raw={Home:''};
    const factory=vm.runInNewContext(source+'\ncreateBrowserVisitorPreferences;',{Date:{now:()=>now}});
    const api={getBookmarks:()=>raw,getHomeLocationAddress:()=>'',removeBookmark(name){delete raw[name];},addBookmark(){},setHomeLocationToAddress(){}};
    const worker=factory({initial:{bookmarks:[]},api,authority:()=>authority,revision:()=>1,send:message=>messages.push(message)});
    worker.restore();worker.poll();assert.equal(messages.length,1);worker.poll(true);assert.equal(messages.length,1);
    raw.New='overte://new';now=1500;worker.poll();assert.equal(messages.length,1);now=2000;worker.poll();assert.equal(messages.length,2);
    authority=null;worker.poll(true);assert.equal(messages.length,2);
    authority='new-approved-revision';worker.poll(true);assert.equal(messages.length,3,'Unchanged preferences are resent after reapproval because previously queued data may have been revoked');
    authority=null;raw.Late='overte://late';worker.poll(true);assert.equal(messages.length,3);
    authority='approved';for(let i=0;i<102;i++)raw['n'+i]='overte://world';worker.poll(true);worker.poll(true);
    assert.equal(messages.filter(message=>message.type==='warning').length,1,'An excessive collection reports one clear warning instead of unbounded payloads');
});
