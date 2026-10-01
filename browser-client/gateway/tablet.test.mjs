// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,copyFile,mkdir,rm,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {TabletSession,validateTabletInput,validateTabletPNG} from './tablet.mjs';

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
test('tablet command whitelists prevent browser-controlled paths, sources and malformed native events',()=>{
    const input=validateTabletInput({type:'tablet',action:'input',event:'press',sequence:1,revision:3,frameSequence:1,x:.2,y:.8,button:0,buttons:1,modifiers:2,path:'/private',qml:'unsafe'});
    assert.deepEqual(input,{type:'tablet',action:'input',sequence:1,revision:3,event:'press',frameSequence:1,x:.2,y:.8,button:0,buttons:1,modifiers:2});
    for(const patch of [{x:Infinity},{y:-.1},{button:8},{buttons:42},{modifiers:16},{event:'evaluate'},{sequence:0}])assert.throws(()=>validateTabletInput({...input,...patch}));
    assert.throws(()=>validateTabletInput({type:'tablet',action:'input',event:'key',key:'file:///x',sequence:1,modifiers:0}));
    assert.equal(validateTabletInput({type:'tablet',action:'input',event:'text',text:'Überte 世界',sequence:1}).text,'Überte 世界');
});
test('actual PNG header dimensions and bounded size are checked',()=>{
    validateTabletPNG(png,1,1);
    assert.throws(()=>validateTabletPNG(png,480,706));
    assert.throws(()=>validateTabletPNG(Buffer.from('notpng'),1,1));
    assert.throws(()=>validateTabletPNG(Buffer.alloc(4*1024*1024+1),1,1));
});
test('authority revision, ordered input, frame acknowledgement and native PNG bridge remain session bound',async()=>{
    const directory=await mkdtemp(join(tmpdir(),'tablet-test-'));const framePath=join(directory,'frame.png');
    let revision=3,active=true;const native=[],browser=[];
    const session=new TabletSession({framePath,sendNative:item=>native.push(item),sendBrowser:item=>browser.push(item),getRevision:()=>revision,isActive:()=>active});
    try{
        session.receive({type:'tablet',action:'open',sequence:1});assert.equal(native[0].revision,3);
        assert.throws(()=>session.receive({type:'tablet',action:'home',sequence:2,revision:2}),/Stale/);
        assert.throws(()=>session.receive({type:'tablet',action:'home',sequence:1,revision:3}),/Repeated/);
        await writeFile(`${framePath}.3.1.png`,png);
        await session.receiveNative({type:'tablet',kind:'frameReady',navigationSequence:1,revision:3,sequence:1,width:1,height:1,surface:'tablet'});
        assert.equal(browser[0].mime,'image/png');assert.deepEqual(Buffer.from(browser[0].data,'base64'),png);
        session.receive({type:'tablet',action:'frameAck',sequence:2,revision:3,frameSequence:1,displayed:true});assert.equal(native.at(-1).action,'frameAck');
        revision=4;await session.receiveNative({type:'tablet',kind:'state',revision:3,visible:true,loading:false,screen:'Home'});assert.equal(browser.length,1);
        active=false;assert.throws(()=>session.receive({type:'tablet',action:'open',sequence:3}),/permissions/);
        session.close();assert.throws(()=>session.receive({type:'tablet',action:'open',sequence:4}),/ended/);
    }finally{session.close();await rm(directory,{recursive:true,force:true});}
});
test('native frame path symlinks are refused before any host bytes reach the browser',async()=>{
    const directory=await mkdtemp(join(tmpdir(),'tablet-test-'));const secret=join(directory,'host.txt'),framePath=join(directory,'frame.png');
    const browser=[],native=[];const session=new TabletSession({framePath,sendNative:item=>native.push(item),sendBrowser:item=>browser.push(item),getRevision:()=>1,isActive:()=>true});
    try{session.receive({type:'tablet',action:'open',sequence:1});await writeFile(secret,'private host data');await symlink(secret,`${framePath}.1.1.png`);
        await session.receiveNative({type:'tablet',kind:'frameReady',navigationSequence:1,revision:1,sequence:1,width:1,height:1,surface:'tablet'});
        assert.deepEqual(browser.map(item=>item.kind),['error']);assert.equal(native.at(-1).action,'frameAck');assert.ok(!JSON.stringify(browser).includes('private host data'));
    }finally{session.close();await rm(directory,{recursive:true,force:true});}
});
test('visitor clipboard preserves a bounded UTF-8 payload and only returns a requested current-authority selection',async()=>{
    const payload='世界'.repeat(10000),browser=[],native=[];let revision=1;
    assert.equal(validateTabletInput({type:'tablet',action:'input',event:'text',sequence:1,text:payload}).text,payload);
    assert.throws(()=>validateTabletInput({type:'tablet',action:'input',event:'text',sequence:1,text:'界'.repeat(22000)}),/Invalid tablet text/);
    const session=new TabletSession({framePath:'/private/frame',sendNative:item=>native.push(item),sendBrowser:item=>browser.push(item),getRevision:()=>revision,isActive:()=>true});
    session.receive({type:'tablet',action:'input',event:'clipboard',operation:'copy',revision:1,sequence:1});assert.equal(native[0].operation,'copy');
    await session.receiveNative({type:'tablet',kind:'clipboard',revision:1,requestId:2,text:'unsolicited'});assert.equal(browser.length,0);
    await session.receiveNative({type:'tablet',kind:'clipboard',revision:1,requestId:1,text:payload});assert.equal(browser[0].text,payload);
    await session.receiveNative({type:'tablet',kind:'clipboard',revision:1,requestId:1,text:'replayed'});assert.equal(browser.length,1);
    session.receive({type:'tablet',action:'input',event:'clipboard',operation:'cut',revision:1,sequence:2});revision=2;
    await session.receiveNative({type:'tablet',kind:'clipboard',revision:2,requestId:2,text:'old permission'});assert.equal(browser.length,1);session.close();
});

test('worker helpers retain exact startup bytes when checkout files change',async()=>{
    const root=await mkdtemp(join(tmpdir(),'tablet-startup-'));const directory=join(root,'gateway');
    await mkdir(directory);await mkdir(join(root,'shared'));
    await copyFile(new URL('../shared/browser-graphics.mjs',import.meta.url),join(root,'shared/browser-graphics.mjs'));
    try{
        const files=['tablet.mjs','tablet-snapshots.mjs','tablet-files.mjs','tablet-chat.mjs','native-tablet-chat.js','native-tablet.js','tablet-capture.qml'];
        for(const file of files)await copyFile(new URL(file,import.meta.url),join(directory,file));
        const script=await readFile(join(directory,'native-tablet.js')),qml=await readFile(join(directory,'tablet-capture.qml'));
        const {prepareTablet}=await import(pathToFileURL(join(directory,'tablet.mjs')).href);
        await writeFile(join(directory,'native-tablet.js'),'changed after startup');await writeFile(join(directory,'tablet-capture.qml'),'changed after startup');
        const defaults=join(directory,'defaultScripts.js');await writeFile(defaults,'// isolated default scripts fixture');
        const worker=join(directory,'worker');await mkdir(worker);
        const prepared=await prepareTablet(worker,{defaultScriptsURL:pathToFileURL(defaults).href});
        assert.deepEqual(await readFile(new URL(prepared.scriptURL)),script);
        assert.deepEqual(await readFile(new URL(prepared.qmlURL)),qml);
        await assert.rejects(()=>prepareTablet(worker,{defaultScriptsURL:pathToFileURL(defaults).href}),{code:'EEXIST'});
    }finally{await rm(root,{recursive:true,force:true});}
});

test('actual native chat observations are ordered and revoked with their domain authority',async()=>{
    let revision=1,active=true;const output=[],session=new TabletSession({framePath:'/unused',isActive:()=>active,getRevision:()=>revision,sendNative:()=>{},sendBrowser:value=>output.push(value)});
    const record={type:'tablet',kind:'chat',revision:1,sequence:1,channel:'domain',text:'Hello 世界',displayName:'Native visitor',senderId:'12345678-1234-1234-1234-123456789abc'};
    try{await session.receiveNative(record);await session.receiveNative(record);assert.equal(output.length,1);assert.equal(output[0].text,record.text);
        revision=2;await session.receiveNative({...record,sequence:2});assert.equal(output.length,1);await session.receiveNative({...record,revision:2});assert.equal(output.length,2);
        active=false;await session.receiveNative({...record,revision:2,sequence:2});assert.equal(output.length,2);session.close();await session.receiveNative({...record,revision:2,sequence:3});assert.equal(output.length,2);
    }finally{session.close();}
});

test('Graphics results retain only validated fields and current pending requests across authority changes',async()=>{
    let revision=1,active=true;const native=[],browser=[];
    const settings={version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true};
    const session=new TabletSession({framePath:'/unused',getRevision:()=>revision,isActive:()=>active,sendNative:value=>native.push(value),sendBrowser:value=>browser.push(value)});
    const request=(id,extra={})=>({type:'tablet',kind:'graphics',revision,schemaVersion:1,requestId:id,operation:'request',...extra});
    const ack=(id,sequence,extra={})=>({type:'tablet',action:'graphicsResult',revision,sequence,schemaVersion:1,requestId:id,accepted:true,settings,...extra});
    try{
        await session.receiveNative(request(1,{token:'not relayed',path:'/operator'}));
        assert.deepEqual(browser,[{type:'tablet',kind:'graphics',revision:1,schemaVersion:1,requestId:1,operation:'request'}]);
        session.receive(ack(2,1));assert.equal(native.length,0,'Unsolicited result cannot update native controls');
        session.receive(ack(1,2,{token:'not forwarded',path:'/operator'}));
        assert.deepEqual(native,[{...ack(1,2),navigationSequence:0}]);
        session.receive(ack(1,3));assert.equal(native.length,1,'Pending result is consumed once');
        await session.receiveNative(request(1));assert.equal(browser.length,1,'Replayed native request is not reapplied');
        await session.receiveNative(request(2));await session.receiveNative(request(3));
        session.receive(ack(2,4));assert.equal(native.length,1,'A superseded valid response is discarded without closing the world');
        session.receive(ack(3,5));assert.equal(native.length,2);
        await session.receiveNative(request(4));revision=2;
        assert.throws(()=>session.receive({...ack(4,6),revision:1}),/Stale/);
        session.receive(ack(4,6));assert.equal(native.length,2,'Revision reset clears the pending request');
        await session.receiveNative(request(1));session.receive(ack(1,7));assert.equal(native.at(-1).revision,2);
        await session.receiveNative(request(2));active=false;
        assert.throws(()=>session.receive(ack(2,8)),/permissions/);
        const count=browser.length;await session.receiveNative(request(3));assert.equal(browser.length,count);
        session.close();await session.receiveNative(request(4));assert.equal(browser.length,count);
    }finally{session.close();}
});

test('Graphics protocol refuses malformed settings, unsafe request IDs and unimplemented controls',async()=>{
    const valid={type:'tablet',action:'graphicsResult',sequence:1,revision:1,schemaVersion:1,requestId:1,accepted:true,settings:{version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true}};
    for(const patch of [{requestId:0},{requestId:Number.MAX_SAFE_INTEGER+1},{accepted:'yes'},{schemaVersion:2},{message:'x'.repeat(513)},{settings:{...valid.settings,resolutionPercent:15}},{settings:{...valid.settings,shadows:true}}])assert.throws(()=>validateTabletInput({...valid,...patch}));
    const browser=[],session=new TabletSession({framePath:'/unused',getRevision:()=>1,isActive:()=>true,sendNative:()=>{},sendBrowser:value=>browser.push(value)});
    try{await assert.rejects(()=>session.receiveNative({type:'tablet',kind:'graphics',revision:1,schemaVersion:1,requestId:1,operation:'change',field:'shadows',value:true}),/Unsupported/);assert.deepEqual(browser,[]);}finally{session.close();}
});
