// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine native Graphics UI discovery. No entity writes or graphics effect
// acceptance is reported before actual pointer-driven control tests.
import {openActualGraphicsChromium,requireActualGraphicsPage,sizeActualGraphicsPage,readActualScanVisibility} from './tablet-graphics-real-focus.mjs';
import {launchSystemFirefox} from './system-firefox.mjs';
import {measureNativeGraphicsRows,locateNativeGraphicsControls,resolutionSliderX} from './tablet-graphics-geometry.mjs';
import {measureNativeGraphicsPopup,locateNativeGraphicsPopup,stableNativePopup} from './tablet-graphics-popup.mjs';
import {GRAPHICS_SOURCE_SHA256} from '../../gateway/browser-graphics-overrides.mjs';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile,open,lstat,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {constants} from 'node:fs';import {tmpdir} from 'node:os';import {randomUUID} from 'node:crypto';
import {workerProfiles,freshWorkerProfile} from './tablet-create-selection.mjs';
import {assertIsolatedCreateTarget,baselineIdentity} from './tablet-create-contract.mjs';
import {qualifyScan,qualifyApplied,measureNativeResolutionThumb,assertSourcePins,SCAN_SOURCE_PINS} from './tablet-graphics-scan-contract.mjs';
const client=path.resolve(process.env.OVERTE_GRAPHICS_SCAN_SOURCE||path.join(path.dirname(fileURLToPath(import.meta.url)),'../..'));
const repo=path.dirname(client);process.umask(0o077);
const domain='overte://127.0.0.2:45102';
const base=process.env.OVERTE_LAB_URL||'http://127.0.0.1:8090';
const endpoint=new URL(base);assert(['127.0.0.1','localhost'].includes(endpoint.hostname),'Only the isolated local gateway is admitted for editor discovery');
const systemFirefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
assertIsolatedCreateTarget(base,domain);
const directory=process.env.OVERTE_GRAPHICS_SCAN_OUTPUT||path.join(repo,'build/browser-lab/evidence/graphics-scan',randomUUID());
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
const sources=['gateway/native-tablet.js','gateway/tablet-capture.qml','gateway/native-browser-graphics.js','gateway/browser-graphics-overrides.mjs','gateway/tablet.mjs','gateway/server.mjs','gateway/native-bridge.js','gateway/worker-sandbox.mjs','gateway/native-worker-refresh-readback.js','gateway/native-worker-refresh-probe.js','dist/index.html','src/main.ts','src/world.ts','src/browser-graphics-controller.ts','src/browser-graphics-target.ts','shared/browser-graphics.mjs','tests/integration/tablet-graphics.mjs','tests/integration/tablet-graphics-geometry.mjs','tests/integration/tablet-graphics-popup.mjs','src/tablet.ts','src/tablet-protocol.ts','src/browser-graphics-intent.ts','src/graphics-environment-scan.ts','src/graphics-environment-panel.ts','src/graphics-scan-frames.ts','shared/browser-graphics-local.mjs','tests/integration/system-firefox.mjs','tests/integration/tablet-graphics-real-focus.mjs','tests/integration/tablet-create-selection.mjs','tests/integration/tablet-create-contract.mjs'];
async function distManifest(){const directory=path.join(client,'dist/assets'),names=(await readdir(directory)).filter(n=>/^[A-Za-z0-9_.-]+\.js$/.test(n)).sort();assert(names.length>0&&names.length<=128);const entries={};for(const name of names){const f=await open(path.join(directory,name),constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const st=await f.stat();assert(st.isFile()&&st.size<=16*1024*1024);const h=createHash('sha256'),b=Buffer.alloc(65536);let pos=0;while(pos<st.size){const r=await f.read(b,0,Math.min(b.length,st.size-pos),pos);assert(r.bytesRead>0);h.update(b.subarray(0,r.bytesRead));pos+=r.bytesRead;}entries[name]={bytes:st.size,sha256:h.digest('hex')};}finally{await f.close();}}return entries;}
async function hashes(){const result={};for(const name of sources)result[name]=createHash('sha256').update(await readFile(path.join(client,name))).digest('hex');return result;}
let browser,page,context,baseline,actualChromium;const profiles=[];let profileBefore;
async function waitOwnedProfilesGone(){const until=Date.now()+12000;while(Date.now()<until){let remaining=0;for(const p of profiles)try{await lstat(p);remaining++;}catch(e){if(e.code!=='ENOENT')throw e;}if(!remaining)return;await delay(100);}throw Error('Owned native profile cleanup deadline');}
async function ownWorker(){
 const after=await workerProfiles(tmpdir()),profile=freshWorkerProfile(profileBefore,after);profiles.push(profile);profileBefore=after;
 const current=baselineIdentity(await page.evaluate(()=>[...window.__editorAudit.entities.values()]));if(baseline)assert.deepEqual(current,baseline);else baseline=current;
 report.runtimeHelpers||=[];const runtime={};const directory=await open(profile,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);
 try{for(const name of ['native-tablet.js','tablet-capture.qml','native-browser-graphics.js']){const f=await open('/proc/self/fd/'+directory.fd+'/'+name,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const st=await f.stat();assert(st.isFile()&&st.size<=256*1024);const b=Buffer.alloc(st.size),read=await f.read(b,0,b.length,0);assert.equal(read.bytesRead,st.size);const expected=await readFile(path.join(client,'gateway',name));assert(b.equals(expected),'Exact current startup-cached worker helper');runtime[name]=createHash('sha256').update(b).digest('hex');}finally{await f.close();}}const f=await open('/proc/self/fd/'+directory.fd+'/bridge.js',constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const st=await f.stat();assert(st.isFile()&&st.size<=1024*1024);const b=Buffer.alloc(st.size),r=await f.read(b,0,b.length,0);assert.equal(r.bytesRead,st.size);const expected=await readFile(path.join(client,'gateway/native-bridge.js'),'utf8');assert.equal(b.toString().split(expected).length,2,'Current approved native bridge appears exactly once');runtime.bridgeSHA256=createHash('sha256').update(b).digest('hex');}finally{await f.close();}}finally{await directory.close();}
 report.runtimeHelpers.push(runtime);assert(await page.evaluate(()=>document.getElementById('microphone').getAttribute('aria-pressed')==='false'));
}

try{
    await mkdir(directory,{mode:0o700});report.sourceHashes.start=await hashes();report.distAssetsStart=await distManifest();assertSourcePins(report.sourceHashes.start);report.driverSHA256=createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex');report.contractSHA256=createHash('sha256').update(await readFile(new URL('./tablet-graphics-scan-contract.mjs',import.meta.url))).digest('hex');profileBefore=await workerProfiles(tmpdir());report.nativePackageSources={start:await installedHashes()};
    assert.equal(process.env.OVERTE_LAB_BROWSER_HEADED,'1','Stock headed hardware qualification required');
    if(systemFirefox){browser=await launchSystemFirefox({headless:false,env:process.env,syntheticMicrophone:false});context=await browser.newContext({viewport:{width:1280,height:900}});}
    else{actualChromium=await openActualGraphicsChromium({executablePath:process.env.OVERTE_LAB_CHROMIUM,env:{...process.env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})}});browser=actualChromium.browser;context=actualChromium.context;report.browserFocusOwnership=actualChromium.readOwnership();}
    report.browserVersion=browser.version();page=await context.newPage();
    if(!systemFirefox){report.browserFocusScope=requireActualGraphicsPage(context,page);report.browserViewport=await sizeActualGraphicsPage(context,page,{width:1280,height:900});}
    await page.bringToFront();
    report.observedDistAssets=[];page.on('response',response=>{try{const u=new URL(response.url());if(u.origin===endpoint.origin&&u.pathname.startsWith('/assets/')&&u.pathname.endsWith('.js')){const name=u.pathname.slice('/assets/'.length);if(!report.observedDistAssets.includes(name)){assert(Object.hasOwn(report.distAssetsStart,name));assert(report.observedDistAssets.length<128);report.observedDistAssets.push(name);}}}catch{report.distObservationRefused=true;}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
        const Original=window.WebSocket;window.__editorAudit={frames:[],frame:null,states:[],warnings:[],entityCount:0,graphics:[],graphicsResults:[],graphicsChanges:[],graphicsApplied:[],entities:new Map(),trustedToolbar:[],censored:false};
        document.addEventListener('click',event=>{const button=event.target instanceof Element?event.target.closest('button'):null;if(!button||!['Scan browser graphics','Apply optional resolution'].includes(button.textContent))return;const a=window.__editorAudit;a.trustedToolbar.push({name:button.textContent,trusted:event.isTrusted===true,at:performance.now(),revision:a.frame?.revision,sequence:a.frame?.sequence});if(a.trustedToolbar.length>16){a.censored=true;a.trustedToolbar.shift();}},{capture:true});
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);window.__editorAudit.frames=[];window.__editorAudit.frame=null;window.__editorAudit.states=[];window.__editorAudit.graphics=[];window.__editorAudit.graphicsResults=[];window.__editorAudit.graphicsChanges=[];window.__editorAudit.graphicsApplied=[];window.__editorAudit.entities=new Map();this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{
                const value=JSON.parse(event.data),audit=window.__editorAudit;
                if(value.type==='warning')audit.warnings.push(value.message);
                if(value.type==='tablet'&&value.kind==='graphics'){audit.graphics.push({...value,observedAt:performance.now()});if(audit.graphics.length>64){audit.censored=true;audit.graphics.shift();}}
                if(value.type==='entities'){audit.entityCount=value.entities.length;audit.entities=new Map(value.entities.map(e=>[e.id,e]));}
                if(value.type==='entityUpdates'){for(const id of value.removed)audit.entities.delete(id);for(const e of value.entities)audit.entities.set(e.id,e);}
                if(value.type==='tablet'&&value.kind==='graphicsApplied'){audit.graphicsApplied.push({...value,observedAt:performance.now()});if(audit.graphicsApplied.length>64){audit.censored=true;audit.graphicsApplied.shift();}}
                if(value.type==='tablet'&&value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>8)audit.frames.shift();}
                if(value.type==='tablet'&&value.kind==='state'){audit.states.push({screen:value.screen,visible:value.visible});if(audit.states.length>20)audit.states.shift();}
            }catch{}});}
            send(data){if(typeof data==='string'){try{const value=JSON.parse(data);if(value.type==='tablet'&&value.action==='graphicsResult'){window.__editorAudit.graphicsResults.push({...value,observedAt:performance.now()});if(window.__editorAudit.graphicsResults.length>64){window.__editorAudit.censored=true;window.__editorAudit.graphicsResults.shift();}}if(value.type==='tablet'&&value.action==='graphicsChange'){window.__editorAudit.graphicsChanges.push({...value,observedAt:performance.now()});if(window.__editorAudit.graphicsChanges.length>16){window.__editorAudit.censored=true;window.__editorAudit.graphicsChanges.shift();}}if(value.type==='tablet'&&value.action==='frameAck'&&value.displayed===true){const audit=window.__editorAudit;const frame=audit.frames.find(item=>item.sequence===value.frameSequence&&item.revision===value.revision);if(frame)audit.frame=frame;}}catch{}}super.send(data);}
        };
    });
    await page.goto(base);await page.locator('#domain').fill(domain);await page.locator('#name').fill('Browser Graphics Audit');await page.locator('#join').click();report.step='join';
    await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});await ownWorker();
    await page.locator('#tablet').click();await page.waitForFunction(()=>window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    async function capture(name){
        const frame=await page.evaluate(()=>window.__editorAudit.frame);assert(frame?.tabletRect,'Actual native tablet frame is displayed');assert.equal(frame.effects?.muted,true,'Actual owned native microphone stays muted during graphics proof');
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
    async function paintedPopup(expectedIndex,afterSequence,label){
        const deadline=Date.now()+15000;let stable=null,last=null;
        while(Date.now()<deadline){
            assert(await page.evaluate(()=>window.__overte.connected),'Native popup test requires the same live domain session');
            const frame=await page.evaluate(()=>window.__editorAudit.frame);
            if(frame&&frame.sequence>afterSequence){
                const rows=await canvas.evaluate(measureNativeGraphicsPopup,frame.tabletRect);
                const popup=locateNativeGraphicsPopup(rows);
                const current=await page.evaluate(()=>window.__editorAudit.frame);
                // Pixel measurements must belong to the exact displayed frame.
                if(current.sequence===frame.sequence&&current.revision===frame.revision){
                    last={sequence:frame.sequence,revision:frame.revision,popup};
                    if(expectedIndex===null){
                        if(!popup&&stable&&!stable.popup&&frame.sequence>stable.sequence&&frame.revision===stable.revision)return last;
                        stable=!popup?last:null;
                    }else if(popup&&popup.highlightedIndex===expectedIndex){
                        if(stableNativePopup(stable,last)){report.popupReadiness||=[];report.popupReadiness.push({label,...last});return last;}
                        stable=last;
                    }else stable=null;
                }
            }
            await delay(100);
        }
        report.popupFailure={label,expectedIndex,last};throw Error('The genuine native resolution popup did not paint stable row '+expectedIndex+' within 15000 milliseconds');
    }
    async function openPopup(previous,label){
        await page.keyboard.press('Escape');await paintedPopup(null,previous.sequence,label+'-closed');
        const closed=await page.evaluate(()=>window.__editorAudit.frame);
        // Hit the actual native indicator, not selectable caption text. Move
        // inside the native header afterwards so hover cannot select a row.
        await tapHome(447,geometry.profile.y);
        const bounds=await canvas.boundingBox(),frame=await page.evaluate(()=>window.__editorAudit.frame),r=frame.tabletRect;
        assert(bounds);await page.mouse.move(bounds.x+(r.x+450*r.width/480)/frame.width*bounds.width,bounds.y+(r.y+30*r.height/706)/frame.height*bounds.height);
        const value=await page.evaluate(()=>window.__overte.graphics.resolutionPercent),index=[100,80,60].indexOf(value);
        return paintedPopup(index<0?3:index,closed.sequence,label+'-open');
    }
    async function preset(index,value){
        report.step='genuine native combo '+value;const previous=await beforeInput();
        let popup=await openPopup(previous,'preset-'+value);
        await page.keyboard.press('Home');popup=await paintedPopup(0,popup.sequence,'preset-'+value+'-home');
        for(let step=1;step<=index;step++){await page.keyboard.press('ArrowDown');popup=await paintedPopup(step,popup.sequence,'preset-'+value+'-row-'+step);}
        await capture('preset-'+value+'-painted-popup');await page.keyboard.press('Enter');
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
    const customPopup=await openPopup(previous,'custom-70');assert.equal(customPopup.popup.highlightedIndex,3);await capture('custom-70-popup');await page.keyboard.press('ArrowUp');await paintedPopup(2,customPopup.sequence,'custom-arrow-up-row-2');await capture('custom-up-to-60-popup');await page.keyboard.press('Enter');
    await settled('resolutionPercent',60,previous,'custom-readback-up-to-60');
    await control('resolutionPercent',70,resolutionSliderX(70),geometry.resolutionPercent.y);
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected);
    report.step='reconnect persisted browser controls';await page.locator('#join').click();await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});await ownWorker();
    const restored=await page.evaluate(()=>({settings:window.__overte.graphics,width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight}));
    assert.equal(restored.settings.fieldOfView,130);assert.equal(restored.settings.resolutionPercent,70);assertBuffer(restored,70);report.restored=restored;
    report.step='reconnected native Graphics page';await page.locator('#tablet').click();await page.waitForFunction(()=>window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});await delay(1000);await home();previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(100,600);await newFrame({sequence:previous.sequence,data:previous.data});await delay(1000);previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(200,155);await newFrame({sequence:previous.sequence,data:previous.data});await delay(2000);await capture('graphics-reconnected');
    geometry=await controls();await control('fieldOfView',70,357,geometry.fieldOfView.y);await preset(0,100);
    assertBuffer(await page.evaluate(()=>({width:window.__overte.performance.drawingBufferWidth,height:window.__overte.performance.drawingBufferHeight})),100);
    report.resolutionProfileAcceptance=true;report.profileSequence=[100,80,60,100,70,60,70,100];
    assert.equal(errors.length,0,errors.join('\n'));assert.equal(report.distObservationRefused,undefined);assert(report.observedDistAssets.length>0,'At least the actual main bundle must be observed');report.assertions.push('Genuine native resolution combo100/80/60, Custom70 readback, sliders/switch input change actual browser target state and framebuffer dimensions; persisted settings survive leave/reconnect. Actual local-light pixels and constrained-camera pixels remain separate acceptance.');
    assert.equal(report.controlEffects.length,17,'All original seventeen actual native effects are mandatory');report.controlAcceptance=true;
    await scannerJourney();
    assert.equal(errors.length,0,errors.join('\n'));assert.equal(report.distObservationRefused,undefined);
    async function scannerJourney(){
        const scanButton=page.getByRole('button',{name:'Scan browser graphics',exact:true}),applyButton=page.getByRole('button',{name:'Apply optional resolution',exact:true});
        const read=()=>page.evaluate(()=>{const a=window.__editorAudit,p=window.__overte.performance,state=a.states.at(-1);return {settings:window.__overte.graphics,width:p.drawingBufferWidth,height:p.drawingBufferHeight,nativeDPR:devicePixelRatio,rendered:p.renderedFrames,observedAt:performance.now(),connected:window.__overte.connected,censored:a.censored,commands:{changes:a.graphicsChanges.length,requests:a.graphics.length,results:a.graphicsResults.length},frame:a.frame?{sequence:a.frame.sequence,revision:a.frame.revision}:null,home:a.frame?{sequence:a.frame.sequence,revision:a.frame.revision,visible:state?.visible,screen:state?.screen}:null,status:document.querySelector('[aria-label="Browser graphics environment"] [role=status]')?.textContent,applyDisabled:Array.from(document.querySelectorAll('button')).find(e=>e.textContent==='Apply optional resolution')?.disabled};});
        report.step='genuine browser Scan';const before=await read(),clickCount=await page.evaluate(()=>window.__editorAudit.trustedToolbar.length);
        await scanButton.click();await page.waitForFunction(()=>window.__overte.connected&&!window.__overte.tabletVisible,undefined,{timeout:5000});
        await page.waitForFunction(()=>document.querySelector('[aria-label="Browser graphics environment"] [role=status]')?.textContent.includes('observed'),undefined,{timeout:10000});
        await page.waitForFunction(sequence=>window.__overte.tabletVisible&&window.__editorAudit.frame?.sequence>sequence&&window.__editorAudit.states.at(-1)?.screen==='Home',before.frame.sequence,{timeout:30000});
        const after=await read(),sample=qualifyScan(before,after);const scanEvent=await page.evaluate(index=>window.__editorAudit.trustedToolbar[index],clickCount);assert.equal(scanEvent.name,'Scan browser graphics');assert.equal(scanEvent.trusted,true);report.scan={before,after,sample};await capture('scan-returned-native-home');await page.screenshot({path:path.join(directory,'scan-result-visible.png')});
        if(sample.optional===null){assert.equal(after.applyDisabled,true);report.optionalApplyQualified=false;report.optionalApplyPendingReason='The actual sampled managed view did not offer a reduction; no synthetic slow sample is allowed.';}
        else{
            report.step='genuine optional Apply';assert.equal(after.applyDisabled,false);const changes=await page.evaluate(()=>window.__editorAudit.graphicsChanges.length);await applyButton.click();
            await page.waitForFunction(count=>{const a=window.__editorAudit;return a.graphicsChanges.length===count+1&&a.graphicsApplied.some(v=>v.browserRequestId===a.graphicsChanges.at(-1).browserRequestId);},changes,{timeout:10000});
            const applied=await page.evaluate(()=>{const a=window.__editorAudit,intent=a.graphicsChanges.at(-1),request=a.graphics.find(r=>r.browserRequestId===intent.browserRequestId),ack=a.graphicsResults.find(r=>r.requestId===request?.requestId&&r.revision===request.revision),completion=a.graphicsApplied.find(r=>r.browserRequestId===intent.browserRequestId);return {intent,request,ack,completion,settings:window.__overte.graphics,persisted:JSON.parse(localStorage.getItem('overte.browser.graphics.v1')),connected:window.__overte.connected,censored:a.censored};});
            qualifyApplied(before,applied,sample.optional);assertBuffer(await read(),sample.optional);report.optionalApply={...applied};
            const lastClick=await page.evaluate(()=>window.__editorAudit.trustedToolbar.at(-1));assert.equal(lastClick.name,'Apply optional resolution');assert.equal(lastClick.trusted,true);
            await home();previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(100,600);await newFrame(previous);await delay(1000);previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(200,155);await newFrame(previous);await delay(2000);geometry=await controls();
            const thumb=await canvas.evaluate(measureNativeResolutionThumb,{rect:(await page.evaluate(()=>window.__editorAudit.frame)).tabletRect,y:geometry.resolutionPercent.y});assert(Math.abs(thumb.x-resolutionSliderX(sample.optional))<=2,'Actual native cached slider handle agrees with the confirmed value');
            const prePopup=await beforeInput(),popup=await openPopup(prePopup,'scanner-confirmed-profile');const expectedIndex=[100,80,60].indexOf(sample.optional);assert.equal(popup.popup.highlightedIndex,expectedIndex<0?3:expectedIndex);await capture('scan-applied-native-profile');await page.keyboard.press('Escape');await paintedPopup(null,popup.sequence,'scanner-profile-closed');report.optionalApplyQualified=true;
        }
        assert.deepEqual(baselineIdentity(await page.evaluate(()=>[...window.__editorAudit.entities.values()])),baseline);assert(await page.evaluate(()=>document.getElementById('microphone').getAttribute('aria-pressed')==='false'));
        report.step='real hidden-tab scan cancellation';await home();const other=await context.newPage();report.hiddenPhase={phase:'initialVisible',initialVisible:false,tabletHidden:false,documentHidden:false,cancelStatus:false};
        try{await other.goto('about:blank');await page.bringToFront();await page.waitForFunction(()=>document.visibilityState==='visible',undefined,{timeout:5000});report.hiddenPhase.initialVisible=true;report.hiddenPhase.phase='tabletHidden';await scanButton.click();await page.waitForFunction(()=>!window.__overte.tabletVisible,undefined,{timeout:5000});report.hiddenPhase.tabletHidden=true;report.hiddenPhase.phase='documentHidden';await other.bringToFront();await page.waitForFunction(()=>document.visibilityState==='hidden',undefined,{timeout:5000});report.hiddenPhase.documentHidden=true;report.hiddenPhase.phase='cancelStatus';await page.waitForFunction(()=>document.querySelector('[aria-label="Browser graphics environment"] [role=status]')?.textContent.toLowerCase().includes('cancel'),undefined,{timeout:10000});report.hiddenPhase.cancelStatus=true;report.hiddenPhase.phase='complete';}
        catch(error){report.hiddenPhase.failureSnapshot=await readActualScanVisibility(page);throw error;}
        finally{await other.close();await page.bringToFront();}
        await page.waitForFunction(()=>document.visibilityState==='visible',undefined,{timeout:5000});await delay(5100);assert(await page.evaluate(()=>window.__overte.connected&&!window.__overte.tabletVisible));report.hiddenCancellation=true;
        report.step='leave during actual scan';await page.locator('#tablet').click();await page.waitForFunction(()=>window.__overte.tabletVisible&&window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});await scanButton.click();await page.waitForFunction(()=>!window.__overte.tabletVisible,undefined,{timeout:5000});await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected,undefined,{timeout:10000});await delay(5100);assert(await page.evaluate(()=>!window.__overte.connected&&!window.__overte.tabletVisible));report.leaveCancellation=true;
        profileBefore=await workerProfiles(tmpdir());await page.locator('#join').click();await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});await ownWorker();
        assert.deepEqual(baselineIdentity(await page.evaluate(()=>[...window.__editorAudit.entities.values()])),baseline);await page.locator('#tablet').click();await page.waitForFunction(()=>window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});
        if(sample.optional!==null){assert.equal((await read()).settings.resolutionPercent,sample.optional);await home();previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(100,600);await newFrame(previous);await delay(1000);previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(200,155);await newFrame(previous);await delay(2000);geometry=await controls();const p=await beforeInput(),popup=await openPopup(p,'scanner-rejoined-profile');assert.equal(popup.popup.highlightedIndex,[100,80,60].includes(sample.optional)?[100,80,60].indexOf(sample.optional):3);await capture('scan-persisted-native-profile');await page.keyboard.press('Escape');await paintedPopup(null,popup.sequence,'scanner-rejoined-profile-closed');report.optionalPersistenceQualified=true;}
        report.scanAcceptance=true;
    }


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
    if(page&&baseline)try{assert.deepEqual(baselineIdentity(await page.evaluate(()=>[...window.__editorAudit.entities.values()])),baseline);report.sevenBaselineUnchanged=true;}catch{report.completed=false;report.baselineChanged=true;process.exitCode=1;}
    if(page)try{await page.bringToFront();if(await page.evaluate(()=>window.__overte?.tabletVisible))await page.getByRole('button',{name:'Close tablet',exact:true}).click();if(await page.evaluate(()=>window.__overte?.connected)){await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte?.connected,undefined,{timeout:10000});}}catch{report.completed=false;report.leaveFailed=true;process.exitCode=1;}
    try{await browser?.close();if(actualChromium){report.browserFocusOwnership=actualChromium.readOwnership();assert.equal(report.browserFocusOwnership.ownedLeaderClosed,true,'Actual owned stock Chromium launch leader exits');}}catch{report.browserCleanupRefused=true;report.completed=false;process.exitCode=1;if(actualChromium)report.browserFocusOwnership=actualChromium.readOwnership();}
    try{await waitOwnedProfilesGone();report.cleanupVerified=profiles.length>0;report.ownedProfileCount=profiles.length;}catch{report.cleanupVerified=false;report.completed=false;process.exitCode=1;}
    try{
        report.sourceHashes.end=await hashes();report.distAssetsEnd=await distManifest();assert.deepEqual(report.distAssetsStart,report.distAssetsEnd,'Exact compiled main/worker assets remain frozen');report.nativePackageSources.end=await installedHashes();
        assert.deepEqual(report.nativePackageSources.start,report.nativePackageSources.end,'All six installed native sources remained pinned');
        assert.deepEqual(report.sourceHashes.start,report.sourceHashes.end,'Sources remained frozen during UI discovery');
        report.sourceAttestation=true;
    }catch(error){report.sourceAttestation=false;report.completed=false;report.attestationFailure=String(error?.message||error);process.exitCode=1;}
    report.finishedAt=new Date().toISOString();const text=JSON.stringify(report,null,2)+'\n';
    await writeFile(path.join(directory,'report.private.json'),text,{mode:0o600,flag:'wx'});
    console.log(JSON.stringify({completed:report.completed,controlAcceptance:report.controlAcceptance===true,scanAcceptance:report.scanAcceptance===true,optionalApplyQualified:report.optionalApplyQualified===true,cleanupVerified:report.cleanupVerified,sourceAttestation:report.sourceAttestation,reportSHA256:createHash('sha256').update(text).digest('hex')}));
}
