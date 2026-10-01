// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real installed Places GUI, separate gateway, fresh native workers and public read-only admission.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {terminateProcess} from '../../gateway/process-lifecycle.mjs';
import {resolvePublicPlace} from '../../gateway/public-places.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const output=path.join(root,'build/browser-hub-lab/places-proof');
const port=process.env.OVERTE_PLACES_TEST_PORT||'8093',endpoint=`http://127.0.0.1:${port}`;
const input=JSON.parse(await readFile(process.env.OVERTE_PUBLIC_TEST_ENV||path.join(root,'build/browser-hub-lab/gateway/environment-private.json'),'utf8'));
const environment={...(input.env||input),OVERTE_GATEWAY_PORT:port,OVERTE_GATEWAY_HOST:'127.0.0.1',OVERTE_GATEWAY_ORIGINS:endpoint,
    OVERTE_GATEWAY_MAX_SESSIONS:'1',OVERTE_GATEWAY_XVFB:path.join(root,'build/browser-lab/host-tools/usr/bin/Xvfb'),
    OVERTE_GATEWAY_SLIRP:path.join(root,'build/browser-native-net/root/usr/bin/slirp4netns')};
environment.OVERTE_GATEWAY_ASSET_ORIGINS=[...new Set((environment.OVERTE_GATEWAY_ASSET_ORIGINS||'').split(',').filter(Boolean).concat(['https://content.overte.org','https://raw.githubusercontent.com','http://127.0.0.1:45110']))].join(',');
environment.QML2_IMPORT_PATH=[...new Set((environment.QML2_IMPORT_PATH||'').split(':').filter(Boolean).concat([path.join(root,'build/browser-lab/native-input/qml')]))].join(':');
const managed='overte://127.0.0.2:45102',preferenceKey='overte.browser.visitor-preferences.v1';
const homeOnly=process.env.OVERTE_PLACES_HOME_ONLY==='1';
const files=['gateway/server.mjs','gateway/native-bridge.js','gateway/native-visitor-preferences.js','gateway/navigation.mjs',
    'gateway/places-override.mjs','gateway/worker-sandbox.mjs','shared/visitor-preferences.mjs','dist/index.html'];
const report={startedAt:new Date().toISOString(),completed:false,publicMicrophoneEnabled:false,publicWorldMutations:0,assertions:[],steps:[],events:[]};
function phase(name){const event={phase:name,at:new Date().toISOString()};report.events.push(event);console.log(JSON.stringify(event));}
async function hashes(){return Object.fromEntries(await Promise.all(files.map(async file=>[file,createHash('sha256').update(await readFile(path.join(root,'browser-client',file))).digest('hex')])));}
let gateway,browserServer,browser,page,cleaningUp=false,browserDiagnostics='';
try{
    await mkdir(output,{recursive:true});report.startSourceSHA256=await hashes();
    gateway=spawn(process.execPath,['gateway/server.mjs'],{cwd:path.join(root,'browser-client'),env:environment,stdio:['ignore','pipe','pipe']});
    gateway.stderr.on('data',()=>{});
    await Promise.race([once(gateway.stdout,'data'),once(gateway,'exit').then(()=>{throw Error('The isolated Places gateway failed to start');})]);
    const browserEnv={...process.env};if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)browserEnv.LD_LIBRARY_PATH=process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH;
    if(process.env.OVERTE_LAB_BROWSER_DISPLAY)browserEnv.DISPLAY=process.env.OVERTE_LAB_BROWSER_DISPLAY;
    browserServer=await chromium.launchServer({headless:!process.env.OVERTE_LAB_BROWSER_DISPLAY,args:['--mute-audio','--disable-dev-shm-usage'],env:browserEnv,
        ...(process.env.OVERTE_LAB_CHROMIUM?{executablePath:process.env.OVERTE_LAB_CHROMIUM}:{})});
    const browserProcess=browserServer.process();report.ownedBrowserPID=browserProcess.pid;
    browserProcess.stderr?.on('data',data=>{browserDiagnostics=(browserDiagnostics+data).slice(-128*1024);});
    browserProcess.once('exit',(code,signal)=>{report.browserProcessExit={code,signal,at:new Date().toISOString(),duringCleanup:cleaningUp};});
    browser=await chromium.connect(browserServer.wsEndpoint());report.browserVersion=browser.version();
    browser.on('disconnected',()=>{if(!cleaningUp)report.browserDisconnectedAt=new Date().toISOString();});
    page=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
    page.on('crash',()=>report.pageCrashedAt=new Date().toISOString());page.on('close',()=>{if(!cleaningUp)report.pageClosedAt=new Date().toISOString();});
    if(homeOnly){report.focusedFinalHome=true;await page.addInitScript(({key,domain})=>localStorage.setItem(key,JSON.stringify({bookmarks:[{name:'Finite Places audit',address:domain}],home:domain})),{key:preferenceKey,domain:managed+'/5.00013,-0.163307,2.99987/0,0,0,1'});}
    await page.addInitScript(()=>{
        const Original=WebSocket;window.__placesAudit={frame:null,frames:[],socket:null,sessionId:'',messages:[],nativePose:null};
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);const a=window.__placesAudit;a.socket=this;a.frame=null;a.frames=[];
                this.addEventListener('message',event=>{if(this!==a.socket||typeof event.data!=='string')return;try{
                    const m=JSON.parse(event.data);if(m.type==='state'&&m.sessionId)a.sessionId=m.sessionId;
                    if(m.type==='tablet'&&m.kind==='frame'){a.frames.push(m);if(a.frames.length>20)a.frames.shift();}
                    if(['navigation','navigationHistory','visitorPreferences','warning'].includes(m.type)){a.messages.push({...m,at:Date.now()});if(a.messages.length>100)a.messages.shift();}
                    if(m.type==='avatars'){const own=m.avatars.find(v=>v.id===m.selfId);if(own)a.nativePose={at:Date.now(),position:own.position};}
                }catch{}});
            }
            send(data){if(typeof data==='string'){try{const m=JSON.parse(data),a=window.__placesAudit;
                if(m.type==='tablet'&&m.action==='frameAck')a.frame=a.frames.find(f=>f.sequence===m.frameSequence&&f.revision===m.revision)||a.frame;
            }catch{}}super.send(data);}
        };
    });
    await page.goto(endpoint);await page.locator('#domain').fill(homeOnly?'overte://overte_hub':managed);await page.locator('#name').fill('Places compatibility observer');await page.locator('#join').click();
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    const state=()=>page.evaluate(()=>({connected:window.__overte.connected,sessionId:window.__placesAudit.sessionId,pose:window.__overte.pose,native:window.__placesAudit.nativePose}));
    async function connected(previous=''){
        await page.waitForFunction(previous=>window.__overte?.connected&&window.__placesAudit.sessionId!==previous&&window.__overte.entityCount>=7,previous,{timeout:90000});
        await page.waitForFunction(()=>{const a=window.__placesAudit.nativePose,p=window.__overte.pose?.position;return a&&p&&Date.now()-a.at<2500&&Math.hypot(a.position.x-p.x,a.position.y-p.y,a.position.z-p.z)<.1;},null,{timeout:20000});
        return state();
    }
    let lastTap=0;
    async function tap(x,y){if(Date.now()-lastTap<300)await page.waitForTimeout(300-(Date.now()-lastTap));const f=await page.evaluate(()=>window.__placesAudit.frame),b=await canvas.boundingBox();assert(f?.tabletRect&&b,'Actual native geometry and displayed canvas are present');const r=f.tabletRect;await page.mouse.click(b.x+(r.x+x*r.width/480)/f.width*b.width,b.y+(r.y+y*r.height/706)/f.height*b.height);lastTap=Date.now();}
    async function changed(action){const before=await page.evaluate(()=>window.__placesAudit.frame?.data);await action();await page.waitForFunction(before=>window.__placesAudit.frame?.data&&window.__placesAudit.frame.data!==before,before,{timeout:20000});}
    async function rendered(action){const before=await page.evaluate(()=>window.__placesAudit.frame?.sequence||0);await action();await page.waitForFunction(before=>(window.__placesAudit.frame?.sequence||0)>=before+2,before,{timeout:15000});}
    async function capture(name){const f=await page.evaluate(()=>window.__placesAudit.frame);assert(f?.data);await writeFile(path.join(output,name+'.png'),Buffer.from(f.data,'base64'));}
    async function places(){await page.locator('#tablet').click();await page.waitForFunction(()=>window.__placesAudit.frame?.tabletRect,null,{timeout:30000});await changed(()=>tap(100,460));await page.waitForTimeout(1500);}
    async function committedText(text,x=220,y=20){await rendered(()=>tap(x,y));await rendered(()=>page.keyboard.press('Control+a'));await page.getByLabel('Native tablet text input').evaluate((element,text)=>element.dispatchEvent(new CompositionEvent('compositionend',{data:text,bubbles:true})),text);await rendered(()=>Promise.resolve());}
    async function navigation(action,type='navigation'){
        const before=await state(),count=await page.evaluate(()=>window.__placesAudit.messages.length);await action();
        await page.waitForFunction(({count,type})=>window.__placesAudit.messages.slice(count).some(m=>m.type===type),{count,type},{timeout:20000});
        const after=await connected(before.sessionId),message=await page.evaluate(({count,type})=>window.__placesAudit.messages.slice(count).find(m=>m.type===type),{count,type});
        assert.notEqual(after.sessionId,before.sessionId,'The native worker session changes on every Places admission');
        const error=Math.hypot(...['x','y','z'].map(axis=>after.pose.position[axis]-after.native.position[axis]));
        assert(error<.1,'Fresh browser and actual native avatar agree');report.steps.push({type,domain:message.domain,direction:message.direction,nativePoseDifferenceMeters:error,at:new Date().toISOString()});phase(`${type} admitted`);return after;
    }
    await connected();phase('Initial world connected');if(!homeOnly){await places();await capture('initial-places');
    await committedText('127.0.0.2:45102/5,1.5,3/0,0,0,1');
    const finite=await navigation(()=>tap(450,20));assert(Math.abs(finite.pose.position.x-5)<.1&&Math.abs(finite.pose.position.z-3)<.1);report.assertions.push('Genuine Places address bar admits a finite managed viewpoint into a fresh synchronized worker');
    await places();await changed(()=>tap(305,79));await changed(()=>tap(225,56));
    await committedText('Finite Places audit',250,260);await tap(309,300);
    await page.waitForFunction(key=>JSON.parse(localStorage.getItem(key)||'{"bookmarks":[]}').bookmarks.some(b=>b.name==='Finite Places audit'),preferenceKey,{timeout:15000});
    await rendered(()=>tap(305,79));await page.waitForTimeout(1000);await capture('bookmark-created');const saved=await page.evaluate(key=>JSON.parse(localStorage.getItem(key)),preferenceKey);assert.equal(saved.bookmarks.length,1);phase('Native Bookmark saved in visitor storage');
    await tap(340,56);await page.waitForFunction(key=>!!JSON.parse(localStorage.getItem(key)||'{}').home,preferenceKey,{timeout:15000});await rendered(()=>Promise.resolve());
    await navigation(()=>tap(120,117));report.assertions.push('The real Bookmark dialog saves a bookmark and its card opens a fresh worker');
    await places();await rendered(()=>tap(305,79));await page.waitForTimeout(1000);await capture('bookmark-restored');
    const restored=await page.evaluate(key=>JSON.parse(localStorage.getItem(key)),preferenceKey);assert(restored.bookmarks.some(b=>b.name==='Finite Places audit'));assert(restored.home);
    await navigation(()=>tap(120,117));report.assertions.push('Restored native Bookmark remains clickable across fresh session profiles and Home is retained in visitor browser storage');
    await places();await navigation(()=>tap(52,20),'navigationHistory');
    await places();await navigation(()=>tap(81,20),'navigationHistory');report.assertions.push('Genuine native Back and Forward controls restore committed browser history through new native workers');
    // Use actual fresh DS information in the real GUI; the original app adds hifi:
    // and the gateway must map that pinned authority back to its enabled place.
    const directoryPlace=await resolvePublicPlace('overte_hub',['overte_hub']);
    await places();await committedText(directoryPlace.nativeDomain.replace(/^overte:\/\//,''));
    const publicWorld=await navigation(()=>tap(450,20));assert((await page.locator('#domain').inputValue()).startsWith('overte://overte_hub/'));
    report.assertions.push('Actual Directory IP/port/viewpoint typed into the native Places GUI maps to enabled Hub and receives fresh normal-guest admission');
    }
    await places();await rendered(()=>tap(305,79));await page.waitForTimeout(1000);await capture('public-bookmarks-restored');phase('Stored native Bookmarks displayed in public worker');
    await navigation(()=>tap(24,20));assert((await page.locator('#domain').inputValue()).startsWith(managed));report.assertions.push('Genuine Home in a public worker returns through fresh admission to the stored managed viewpoint');
    await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected);assert.equal(errors.length,0,errors.join('\n'));
    report.completed=true;report.pageErrors=errors;
}catch(error){report.error=error instanceof Error?error.message:String(error);process.exitCode=1;if(page){try{const frame=await page.evaluate(()=>window.__placesAudit.frame);if(frame?.data)await writeFile(path.join(output,'failure-native-ui.png'),Buffer.from(frame.data,'base64'));report.failureState=await page.evaluate(()=>({connected:window.__overte?.connected,notice:document.querySelector('#notice')?.textContent,entityCount:window.__overte?.entityCount}));report.failurePreferences=await page.evaluate(key=>({stored:localStorage.getItem(key),messages:window.__placesAudit.messages.filter(m=>m.type==='visitorPreferences'||m.type==='warning')}),preferenceKey);}catch{}}}
finally{
    cleaningUp=true;
    await browser?.close();await browserServer?.close();if(gateway)await terminateProcess(gateway,12000);report.finishedAt=new Date().toISOString();report.endSourceSHA256=await hashes();
    await writeFile(path.join(output,'browser-private-stderr.log'),browserDiagnostics,{mode:0o600});
    report.sourceUnchanged=JSON.stringify(report.startSourceSHA256)===JSON.stringify(report.endSourceSHA256);if(!report.sourceUnchanged){report.completed=false;report.error='Production source changed during the actual Places journey';process.exitCode=1;}
    await writeFile(path.join(output,homeOnly?'tablet-home.json':'tablet-places.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
