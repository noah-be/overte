// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Drive the genuine native Emote and Avatar apps; inspect actual browser skin bones.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const firefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const directory=path.join(root,'build/browser-hub-lab/tablet-avatar-evidence',firefox?'system-firefox':'chromium');
const emoteOnly=process.env.OVERTE_LAB_AVATAR_FLOW==='emote';
const kimOnly=process.env.OVERTE_LAB_AVATAR_FLOW==='kim';
const report={flow:emoteOnly?'native-emote':kimOnly?'native-avatar-selection':'native-emote-and-avatar-selection',startedAt:new Date().toISOString(),domain:'overte://127.0.0.2:45102',microphoneEnabled:false,assertions:[],completed:false};
const delay=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
let browser,page;const assetFailures=[];const consoleErrors=[];
try{
    await mkdir(directory,{recursive:true});const options={headless:true,args:['--use-angle=swiftshader','--mute-audio']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=path.resolve(root,process.env.OVERTE_LAB_CHROMIUM);
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...process.env,LD_LIBRARY_PATH:path.resolve(root,process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)};
    browser=firefox?await launchSystemFirefox({syntheticMicrophone:false}):await chromium.launch(options);report.browserVersion=browser.version();
    const context=await browser.newContext({viewport:{width:1280,height:900}});page=await context.newPage();if(firefox)await page.bringToFront();
    page.on('response',async response=>{if(response.status()>=400&&response.url().includes('/asset')){const original=new URL(response.url()).searchParams.get('url');assetFailures.push({status:response.status(),asset:original&&new URL(original).origin==='https://content.overte.org'?original:'other permitted asset',error:await response.json().then(body=>body.error).catch(()=>null)});}});page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text().slice(0,512));});
    await page.addInitScript(()=>{
        const Original=window.WebSocket;window.__avatarAudit={own:null,frame:null,state:null,frames:[],errors:[],armChanges:[],baseline:null};
        const canonical=id=>String(id).replace(/[{}]/g,'').toLowerCase();
        const angle=(a,b)=>2*Math.acos(Math.min(1,Math.abs(a.x*b.x+a.y*b.y+a.z*b.z+a.w*b.w)));
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{
                const value=JSON.parse(event.data),audit=window.__avatarAudit;if(value.sessionId)audit.sessionId=value.sessionId;
                if(value.type==='avatars'){
                    audit.own=value.avatars.find(avatar=>canonical(avatar.id)===canonical(value.selfId));
                    if(audit.own&&audit.baseline){for(const name of ['LeftArm','RightArm']){const index=audit.own.jointNames?.indexOf(name),rotation=audit.own.jointRotations?.[index];if(rotation){audit.armChanges.push(angle(rotation,audit.baseline[name]));if(audit.armChanges.length>400)audit.armChanges.shift();}}}
                }
                if(value.type!=='tablet')return;
                if(value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>10)audit.frames.shift();}
                else if(value.kind==='state')audit.state=value;else if(value.kind==='error')audit.errors.push(value.message);
            }catch{}});}
            send(data){if(typeof data==='string')try{const value=JSON.parse(data),audit=window.__avatarAudit;if(value.type==='tablet'&&value.action==='frameAck'&&value.displayed===true)audit.frame=audit.frames.find(frame=>frame.sequence===value.frameSequence&&frame.revision===value.revision)||audit.frame;}catch{}super.send(data);}
        };
    });
    report.step='Join actual isolated world and load original native avatar';await page.goto(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8092');await page.locator('#domain').fill(report.domain);await page.locator('#name').fill('Browser Avatar Audit');await page.locator('#join').click();
    await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7&&window.__overte.avatarRig?.boneCount===67&&window.__avatarAudit.own?.jointNames?.includes('RightArm'),undefined,{timeout:90000});
    report.initialBoneCount=await page.evaluate(()=>window.__overte.avatarRig.boneCount);
    const matched=()=>page.evaluate(()=>{const rig=window.__overte.avatarRig,own=window.__avatarAudit.own;if(!rig||!own)return false;return ['Hips','Head','LeftArm','RightArm'].every(name=>{const index=own.jointNames.indexOf(name),expected=own.jointRotations[index],actual=rig.joints[name]?.orientation;return actual&&expected&&['x','y','z','w'].every(axis=>Math.abs(actual[axis]-expected[axis])<.000001);});});
    assert(await matched(),'Actual applied browser skeleton must agree with the current native joint stream');
    report.assertions.push('The original native default mannequin loads 67 actual browser bones and applies current native Hips/Head/arm rotations');
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    const tap=async(x,y)=>{const frame=await page.evaluate(()=>window.__avatarAudit.frame),bounds=await canvas.boundingBox();assert(frame&&bounds);await page.mouse.click(bounds.x+x/frame.width*bounds.width,bounds.y+y/frame.height*bounds.height);};
    const tapApp=async(x,y)=>{const frame=await page.evaluate(()=>window.__avatarAudit.frame),rect=frame.tabletRect;assert(rect);await tap(rect.x+x*rect.width/480,rect.y+y*rect.height/706);};
    const saveNative=async name=>{const frame=await page.evaluate(()=>window.__avatarAudit.frame);assert(frame?.data);await writeFile(path.join(directory,name),Buffer.from(frame.data,'base64'));};
    report.step='Open native tablet and receive first GUI frame';await page.locator('#tablet').click();await page.waitForFunction(()=>window.__avatarAudit.frame?.tabletRect,undefined,{timeout:30000});await delay(1500);
    if(!kimOnly){report.step='Open genuine Emote app';const homeFrame=await page.evaluate(()=>({sequence:window.__avatarAudit.frame.sequence,data:window.__avatarAudit.frame.data}));await tapApp(380,460);await page.waitForFunction(before=>window.__avatarAudit.state?.screen==='Web'&&window.__avatarAudit.frame.sequence>before.sequence&&window.__avatarAudit.frame.data!==before.data,homeFrame,{timeout:20000});await delay(1500);await saveNative('native-emote.png');
    await page.evaluate(()=>{const audit=window.__avatarAudit;const own=audit.own;audit.baseline=Object.fromEntries(['LeftArm','RightArm'].map(name=>[name,own.jointRotations[own.jointNames.indexOf(name)]]));audit.armChanges=[];});
    report.step='Genuine Qt Waving changes native and browser bones';await tapApp(120,410);
    await page.waitForFunction(()=>window.__avatarAudit.armChanges.some(angle=>angle>.5),undefined,{timeout:10000});
    assert(await matched(),'Waving joint rotations must reach actual browser skin bones');report.maximumArmChangeRadians=await page.evaluate(()=>Math.max(...window.__avatarAudit.armChanges));
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.keyboard.press('v');
    await page.waitForFunction(()=>!window.__overte.tabletVisible&&window.__overte.performance.graphicsActive);
    if(firefox)await page.screenshot({path:path.join(directory,'browser-waving.png')});
    else{const cdp=await page.context().newCDPSession(page);try{const image=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(directory,'browser-waving.png'),Buffer.from(image.data,'base64'));}finally{await cdp.detach();}}
    report.assertions.push('Clicking Waving in the original native Emote app changes native arm rotations by more than 0.5 radians and the real browser mannequin applies those same rotations');}
    if(!emoteOnly){
    report.step='Select genuine Avatar favorite Kim';if(!kimOnly)await page.locator('#tablet').click();await page.getByRole('button',{name:'Home',exact:true}).click();await delay(1500);await tapApp(100,320);await delay(2000);await saveNative('native-avatar-before.png');
    const previous=await page.evaluate(()=>window.__avatarAudit.own.skeletonModelURL),beforeKim=await page.evaluate(()=>window.__avatarAudit.frame.sequence);await tapApp(75,415);
    await page.waitForFunction(sequence=>window.__avatarAudit.frame.sequence>sequence,beforeKim,{timeout:10000});await delay(600);await saveNative('native-avatar-kim-confirmation.png');await tapApp(350,430);
    await page.waitForFunction(previous=>window.__avatarAudit.own.skeletonModelURL!==previous&&window.__avatarAudit.own.skeletonModelURL.includes('/Kim/'),previous,{timeout:30000});
    await page.waitForFunction(()=>window.__overte.avatarRig?.boneCount===58||document.querySelector('#notice')?.textContent.includes('FST request returned'),undefined,{timeout:90000});assert.equal(await page.evaluate(()=>window.__overte.avatarRig?.boneCount),58,'Actual selected Kim rig must load58bones');
    assert(await matched(),'Newly selected actual avatar applies its native skeletal transforms');report.selectedAssets=await page.evaluate(async()=>{const audit=window.__avatarAudit,source=audit.own.skeletonModelURL;const urls=[source,new URL('Kim.fbx',source).href];return await Promise.all(urls.map(async url=>{const response=await fetch(`/api/assets/${audit.sessionId}?url=${encodeURIComponent(url)}`);if(!response.ok)throw Error('Selected avatar asset reread failed');const bytes=await response.arrayBuffer(),digest=await crypto.subtle.digest('SHA-256',bytes);return {filename:new URL(url).pathname.split('/').pop(),bytes:bytes.byteLength,sha256:[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('')};}));});await saveNative('native-avatar-kim.png');report.selectedBoneCount=await page.evaluate(()=>window.__overte.avatarRig.boneCount);report.selectedRendering=await page.evaluate(()=>({render:window.__overte.avatarRender,rig:window.__overte.avatarRig,scale:window.__avatarAudit.own.scale,skeletonOffset:window.__avatarAudit.own.skeletonOffset,jointCount:window.__avatarAudit.own.jointNames.length,performance:window.__overte.performance}));
    await writeFile(path.join(directory,'kim-pose.json'),JSON.stringify(await page.evaluate(()=>({jointNames:window.__avatarAudit.own.jointNames,jointRotations:window.__avatarAudit.own.jointRotations,jointTranslations:window.__avatarAudit.own.jointTranslations,scale:window.__avatarAudit.own.scale,skeletonOffset:window.__avatarAudit.own.skeletonOffset})),null,2)+'\n');
    const beforePresentation=await page.evaluate(()=>window.__overte.performance.renderedFrames);await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.waitForFunction(before=>window.__overte.performance.graphicsActive&&window.__overte.performance.renderedFrames>before,beforePresentation,{timeout:10000});if(kimOnly)await page.keyboard.press('v');await page.waitForFunction(()=>window.__overte.avatarRender?.thirdPerson&&window.__overte.avatarRender?.selfVisible,undefined,{timeout:10000});report.presentedRendering=await page.evaluate(()=>window.__overte.avatarRender);
    let presentedPng;
    if(firefox)presentedPng=Buffer.from(await page.screenshot({path:path.join(directory,'browser-kim.png')}));
    else{const cdp=await page.context().newCDPSession(page);try{const image=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});presentedPng=Buffer.from(image.data,'base64');await writeFile(path.join(directory,'browser-kim.png'),presentedPng);}finally{await cdp.detach();}}
    report.presentedPixels=await page.evaluate(async encoded=>{
        const image=new Image();image.src='data:image/png;base64,'+encoded;await image.decode();
        const surface=document.createElement('canvas');surface.width=image.width;surface.height=image.height;
        const context=surface.getContext('2d');context.drawImage(image,0,0);
        // This actual isolated scene has a flat green pillar behind the visitor.
        // The body-only crop excludes its display-name label and the crosshair.
        const pixels=context.getImageData(610,465,60,180).data;let blueClothing=0,brownHairOrSkin=0;
        for(let index=0;index<pixels.length;index+=4){const [red,green,blue]=pixels.slice(index,index+3);
            if(blue>red*1.25&&blue>green*1.1)blueClothing++;
            if(red>green*1.1&&red>blue*1.3)brownHairOrSkin++;
        }
        return {bodyCrop:{x:610,y:465,width:60,height:180},blueClothing,brownHairOrSkin};
    },presentedPng.toString('base64'));
    assert(report.presentedPixels.blueClothing+report.presentedPixels.brownHairOrSkin>100,'Actual Kim body/texture pixels must be visible below its separate name label');
    report.assertions.push('Selecting Kim in the original native Avatar favorites changes the native skeleton URL, loads its real browser model, and applies the new native joint transforms');
    }
    assert.equal((await page.evaluate(()=>window.__avatarAudit.errors)).length,0);assert(await page.evaluate(()=>window.__overte.connected&&document.querySelector('#microphone').getAttribute('aria-pressed')==='false'));
    await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected&&!window.__overte.tabletVisible);report.completed=true;
}catch(error){report.failure=error instanceof Error?error.message:String(error);process.exitCode=1;
    if(page)try{const frame=await page.evaluate(()=>window.__avatarAudit.frame);if(frame?.data)await writeFile(path.join(directory,'native-failure.png'),Buffer.from(frame.data,'base64'));report.nativeErrors=await page.evaluate(()=>window.__avatarAudit.errors);report.assetFailures=assetFailures;report.consoleErrors=consoleErrors;report.failureState=await page.evaluate(()=>({visibility:document.visibilityState,tabletState:window.__avatarAudit.state,frameCount:window.__avatarAudit.frames.length,events:document.querySelector('#events')?.textContent,performance:window.__overte.performance,rig:window.__overte.avatarRig,warning:document.querySelector('#notice')?.textContent,status:document.querySelector('#status')?.textContent,jointCount:window.__avatarAudit.own?.jointNames?.length,modelSelected:window.__avatarAudit.own?.skeletonModelURL?.includes('/Kim/')}));}catch{}
}finally{await browser?.close();report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,emoteOnly?'tablet-emote.json':'tablet-avatar.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
