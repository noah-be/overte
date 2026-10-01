// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine native Graphics UI discovery. No entity writes or graphics effect
// acceptance is reported before actual pointer-driven control tests.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import {measureNativeGraphicsRows,locateNativeGraphicsControls,resolutionSliderX} from './tablet-graphics-geometry.mjs';
import {GRAPHICS_SOURCE_SHA256} from '../../gateway/browser-graphics-overrides.mjs';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const client=path.join(repo,'browser-client');
const domain='overte://127.0.0.2:45102';
const base=process.env.OVERTE_LAB_URL||'http://127.0.0.1:8090';
const endpoint=new URL(base);assert(['127.0.0.1','localhost'].includes(endpoint.hostname),'Only the isolated local gateway is admitted for editor discovery');
const systemFirefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const directory=path.join(repo,'build/browser-hub-lab/tablet-graphics',systemFirefox?'system-firefox':'chromium');
const defaultScripts=process.env.OVERTE_LAB_DEFAULT_SCRIPTS;
assert(defaultScripts,'Set OVERTE_LAB_DEFAULT_SCRIPTS to the approved installed defaultScripts.js for six-source pin attestation.');
const defaultPath=defaultScripts.startsWith('file:')?fileURLToPath(defaultScripts):defaultScripts;
assert(path.isAbsolute(defaultPath)&&path.basename(defaultPath)==='defaultScripts.js','An absolute installed defaultScripts.js path is required.');
const settingsRoot=path.join(path.dirname(defaultPath),'system/settings');
async function installedHashes(){
    const expectedNames=['Settings.qml','qml/SettingBoolean.qml','qml/SettingComboBox.qml','qml/SettingSlider.qml','qml/pages/GraphicsSettings.qml','settings.js'];
    assert.deepEqual(Object.keys(GRAPHICS_SOURCE_SHA256).sort(),expectedNames,'Exactly six reviewed installed sources are required.');
    const hashes={};for(const name of expectedNames){hashes[name]=createHash('sha256').update(await readFile(path.join(settingsRoot,name))).digest('hex');assert.equal(hashes[name],GRAPHICS_SOURCE_SHA256[name],'Reviewed installed source '+name);}return hashes;
}
const report={startedAt:new Date().toISOString(),step:'launch',completed:false,entityMutations:false,sourceHashes:{},screens:[],assertions:[],functionalAcceptance:false,performanceAcceptance:false,nativePackageSources:{start:null,end:null},controlEffects:[]};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const sources=['gateway/native-tablet.js','gateway/tablet-capture.qml','gateway/native-browser-graphics.js','gateway/browser-graphics-overrides.mjs','gateway/tablet.mjs','gateway/server.mjs','gateway/native-bridge.js','gateway/worker-sandbox.mjs','gateway/native-worker-refresh-readback.js','gateway/native-worker-refresh-probe.js','dist/index.html','src/main.ts','src/world.ts','src/browser-graphics-controller.ts','src/browser-graphics-target.ts','shared/browser-graphics.mjs','tests/integration/tablet-graphics.mjs','tests/integration/tablet-graphics-geometry.mjs'];
async function hashes(){const result={};for(const name of sources)result[name]=createHash('sha256').update(await readFile(path.join(client,name))).digest('hex');return result;}
let browser,page;
try{
    await mkdir(directory,{recursive:true});report.sourceHashes.start=await hashes();report.nativePackageSources={start:await installedHashes()};
    const options={headless:process.env.OVERTE_LAB_BROWSER_HEADED!=='1',args:['--use-angle=swiftshader']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=process.env.OVERTE_LAB_CHROMIUM;
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...process.env,LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH};
    browser=systemFirefox?await launchSystemFirefox({headless:options.headless,env:process.env}):await chromium.launch(options);report.browserVersion=browser.version();
    const context=await browser.newContext({viewport:{width:1280,height:900}});page=await context.newPage();if(systemFirefox)await page.bringToFront();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
        const Original=window.WebSocket;window.__editorAudit={frames:[],frame:null,states:[],warnings:[],entityCount:0,graphics:[],graphicsResults:[]};
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);window.__editorAudit.frames=[];window.__editorAudit.frame=null;window.__editorAudit.states=[];window.__editorAudit.graphics=[];window.__editorAudit.graphicsResults=[];this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{
                const value=JSON.parse(event.data),audit=window.__editorAudit;
                if(value.type==='warning')audit.warnings.push(value.message);
                if(value.type==='tablet'&&value.kind==='graphics')audit.graphics.push(value);
                if(value.type==='entities')audit.entityCount=value.entities.length;
                if(value.type==='tablet'&&value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>8)audit.frames.shift();}
                if(value.type==='tablet'&&value.kind==='state'){audit.states.push({screen:value.screen,visible:value.visible});if(audit.states.length>20)audit.states.shift();}
            }catch{}});}
            send(data){if(typeof data==='string'){try{const value=JSON.parse(data);if(value.type==='tablet'&&value.action==='graphicsResult'){window.__editorAudit.graphicsResults.push(value);if(window.__editorAudit.graphicsResults.length>64)window.__editorAudit.graphicsResults.shift();}if(value.type==='tablet'&&value.action==='frameAck'){const audit=window.__editorAudit;const frame=audit.frames.find(item=>item.sequence===value.frameSequence&&item.revision===value.revision);if(frame)audit.frame=frame;}}catch{}}super.send(data);}
        };
    });
    await page.goto(base);await page.locator('#domain').fill(domain);await page.locator('#name').fill('Browser Graphics Audit');await page.locator('#join').click();report.step='join';
    await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});
    await page.locator('#tablet').click();await page.waitForFunction(()=>window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    async function capture(name){
        const frame=await page.evaluate(()=>window.__editorAudit.frame);assert(frame?.tabletRect,'Actual native tablet frame is displayed');
        await writeFile(path.join(directory,name+'-native-ui.png'),Buffer.from(frame.data,'base64'));
        // Both the Playwright and stock-Firefox drivers can read the actual
        // displayed 2D canvas; no unsupported locator screenshot API is needed.
        const displayed=await canvas.evaluate(element=>element.toDataURL('image/png'));
        await writeFile(path.join(directory,name+'-browser-ui.png'),Buffer.from(displayed.split(',')[1],'base64'));
        report.screens.push({name,screen:await page.evaluate(()=>window.__editorAudit.states.at(-1)?.screen),surface:frame.surface,width:frame.width,height:frame.height,tabletRect:frame.tabletRect,pngSha256:createHash('sha256').update(Buffer.from(frame.data,'base64')).digest('hex')});return frame;
    }
    async function newFrame(previous){await page.waitForFunction(previous=>window.__editorAudit.frame.sequence>previous.sequence&&window.__editorAudit.frame.data!==previous.data,previous,{timeout:20000});}
    async function home(){const previous=await page.evaluate(()=>window.__editorAudit.frame);await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForFunction(sequence=>window.__editorAudit.frame.sequence>sequence&&window.__editorAudit.states.at(-1)?.screen==='Home',previous.sequence,{timeout:20000});await delay(1000);}
    async function tapHome(x,y){const frame=await page.evaluate(()=>window.__editorAudit.frame),rect=frame.tabletRect,bounds=await canvas.boundingBox();assert(bounds,'Native tablet canvas is visible');await page.mouse.click(bounds.x+(rect.x+x*rect.width/480)/frame.width*bounds.width,bounds.y+(rect.y+y*rect.height/706)/frame.height*bounds.height);}
    await delay(2000);await capture('home');
    report.step='actual native Settings';await home();let previous=await page.evaluate(()=>window.__editorAudit.frame);
    await tapHome(100,600);await newFrame({sequence:previous.sequence,data:previous.data});await delay(1000);await capture('settings');
    report.step='actual native Graphics';previous=await page.evaluate(()=>window.__editorAudit.frame);
    await tapHome(200,155);await newFrame({sequence:previous.sequence,data:previous.data});await delay(2500);await capture('graphics');
    report.graphicsRequests=await page.evaluate(()=>window.__editorAudit.graphics);
    report.browserGraphics=await page.evaluate(()=>window.__overte.graphics);
    report.drawingBuffer=await page.evaluate(()=>({width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight}));
    const initial=await page.evaluate(()=>({settings:window.__overte.graphics,width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight,devicePixelRatio:window.devicePixelRatio,cssWidth:document.getElementById('world').clientWidth,cssHeight:document.getElementById('world').clientHeight}));
    assert.equal(initial.settings.resolutionPercent,100,'A fresh context starts at explicit Default100%.');
    const baseRatio=Math.min(initial.devicePixelRatio,2);report.initialDensity={devicePixelRatio:initial.devicePixelRatio,baseRatio,cssWidth:initial.cssWidth,cssHeight:initial.cssHeight};
    function assertBuffer(current,percent){assert.equal(current.width,Math.floor(initial.cssWidth*baseRatio*percent/100));assert.equal(current.height,Math.floor(initial.cssHeight*baseRatio*percent/100));}
    assertBuffer(initial,100);
    async function controls(){const frame=await page.evaluate(()=>window.__editorAudit.frame);return locateNativeGraphicsControls(await canvas.evaluate(measureNativeGraphicsRows,frame.tabletRect));}
    let geometry=await controls();report.actualWidgetGeometry=geometry;
    async function beforeInput(){return page.evaluate(()=>({...window.__editorAudit.frame,graphicsRequestId:window.__editorAudit.graphics.at(-1)?.requestId||0}));}
    async function settled(field,value,previous,name){
        await page.waitForFunction(({field,value})=>window.__overte.graphics?.[field]===value,{field,value},{timeout:15000});
        await page.waitForFunction(({field,value,after})=>{const audit=window.__editorAudit,request=[...audit.graphics].reverse().find(item=>item.requestId>after&&item.operation==='change'&&item.field===field&&item.value===value);return request&&audit.graphicsResults.some(ack=>ack.requestId===request.requestId&&ack.revision===request.revision&&ack.accepted===true&&ack.settings[field]===value);},{field,value,after:previous.graphicsRequestId},{timeout:15000});
        await newFrame({sequence:previous.sequence,data:previous.data});await delay(500);
        const current=await page.evaluate(({field,value,after})=>{const audit=window.__editorAudit,request=[...audit.graphics].reverse().find(item=>item.requestId>after&&item.operation==='change'&&item.field===field&&item.value===value);return {settings:window.__overte.graphics,width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight,request,ack:audit.graphicsResults.find(item=>item.requestId===request.requestId&&item.revision===request.revision)};},{field,value,after:previous.graphicsRequestId});
        assert.equal(current.request.operation,'change');assert.equal(current.request.field,field);assert.equal(current.request.value,value);
        assert.equal(current.ack.accepted,true);assert.deepEqual(current.ack.settings,current.settings);assert.equal(current.settings[field],value);assert(await page.evaluate(()=>window.__overte.connected));
        if(field==='resolutionPercent')assertBuffer(current,value);
        report.controlEffects.push({...current,via:name});await capture(name);return current;
    }
    async function preset(index,value){
        report.step='genuine native combo '+value;const previous=await beforeInput();
        await tapHome(geometry.profile.x,geometry.profile.y);await newFrame({sequence:previous.sequence,data:previous.data});await delay(350);
        await page.keyboard.press('Home');for(let step=0;step<index;step++){await delay(100);await page.keyboard.press('ArrowDown');}await page.keyboard.press('Enter');
        return settled('resolutionPercent',value,previous,'preset-'+value);
    }

    async function control(field,value,x,y){
        report.step='native pointer '+field+' '+value;
        const previous=await beforeInput();
        await tapHome(x,y);
        return settled(field,value,previous,field+'-'+value);
    }
    await control('fieldOfView',20,270,geometry.fieldOfView.y);await control('fieldOfView',130,459,geometry.fieldOfView.y);
    await control('resolutionPercent',50,resolutionSliderX(50),geometry.resolutionPercent.y);await control('resolutionPercent',200,459,geometry.resolutionPercent.y);await control('resolutionPercent',100,resolutionSliderX(100),geometry.resolutionPercent.y);
    await control('localLights',false,geometry.localLights.x,geometry.localLights.y);await control('localLights',true,geometry.localLights.x,geometry.localLights.y);
    await control('cameraClipping',false,geometry.cameraClipping.x,geometry.cameraClipping.y);await control('cameraClipping',true,geometry.cameraClipping.x,geometry.cameraClipping.y);
    //100% is the untouched initial preset; choose every named option explicitly.
    await preset(1,80);await preset(2,60);await preset(0,100);
    await control('resolutionPercent',70,resolutionSliderX(70),geometry.resolutionPercent.y);
    // Opening from Custom70 and moving up once must choose60. This proves
    // actual native readback selected row3, not merely a changed screenshot.
    report.step='native Custom readback';previous=await beforeInput();
    await tapHome(geometry.profile.x,geometry.profile.y);await newFrame({sequence:previous.sequence,data:previous.data});await capture('custom-70-popup');await delay(350);await page.keyboard.press('ArrowUp');await page.keyboard.press('Enter');
    await settled('resolutionPercent',60,previous,'custom-readback-up-to-60');
    await control('resolutionPercent',70,resolutionSliderX(70),geometry.resolutionPercent.y);
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected);
    report.step='reconnect persisted browser controls';await page.locator('#join').click();await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});
    const restored=await page.evaluate(()=>({settings:window.__overte.graphics,width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight}));
    assert.equal(restored.settings.fieldOfView,130);assert.equal(restored.settings.resolutionPercent,70);assertBuffer(restored,70);report.restored=restored;
    report.step='reconnected native Graphics page';await page.locator('#tablet').click();await page.waitForFunction(()=>window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});await delay(1000);await home();previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(100,600);await newFrame({sequence:previous.sequence,data:previous.data});await delay(1000);previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(200,155);await newFrame({sequence:previous.sequence,data:previous.data});await delay(2000);await capture('graphics-reconnected');
    geometry=await controls();await control('fieldOfView',70,357,geometry.fieldOfView.y);await preset(0,100);
    assertBuffer(await page.evaluate(()=>({width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight})),100);
    report.resolutionProfileAcceptance=true;report.profileSequence=[100,80,60,100,70,60,70,100];
    assert.equal(errors.length,0,errors.join('\n'));report.assertions.push('Genuine native resolution combo100/80/60, Custom70 readback, sliders/switch input change actual browser target state and framebuffer dimensions; persisted settings survive leave/reconnect. Actual local-light pixels and constrained-camera pixels remain separate acceptance.');
    report.controlAcceptance=true;

    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected);report.completed=true;
}catch(error){
    report.failure=String(error?.message||error);process.exitCode=1;
    if(page){
        await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});
        report.failureDiagnostics=await page.evaluate(()=>({connected:window.__overte?.connected,
            states:window.__editorAudit?.states,frameMetadata:window.__editorAudit?.frames?.map(({sequence,revision,width,height,surface,tabletRect})=>({sequence,revision,width,height,surface,tabletRect})),
            warningCount:window.__editorAudit?.warnings?.length,graphicsRequestCount:window.__editorAudit?.graphics?.length})).catch(()=>({pageClosed:true}));
        const data=await page.evaluate(()=>window.__editorAudit?.frame?.data).catch(()=>null);
        if(data)await writeFile(path.join(directory,'failure-native-ui.png'),Buffer.from(data,'base64'));
    }
}
finally{
    await browser?.close();
    try{
        report.sourceHashes.end=await hashes();report.nativePackageSources.end=await installedHashes();
        assert.deepEqual(report.nativePackageSources.start,report.nativePackageSources.end,'All six installed native sources remained pinned');
        assert.deepEqual(report.sourceHashes.start,report.sourceHashes.end,'Sources remained frozen during UI discovery');
        report.sourceAttestation=true;
    }catch(error){report.sourceAttestation=false;report.completed=false;report.attestationFailure=String(error?.message||error);process.exitCode=1;}
    report.finishedAt=new Date().toISOString();const text=JSON.stringify(report,null,2)+'\n';
    await writeFile(path.join(directory,'tablet-graphics-'+report.startedAt.replace(/[:.]/g,'-')+'.json'),text);
    await writeFile(path.join(directory,'tablet-graphics.json'),text);console.log(JSON.stringify(report));
}
