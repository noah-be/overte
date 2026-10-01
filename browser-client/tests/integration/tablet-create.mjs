// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real Qt Create input only. Native observer never substitutes a property edit;
// its single-ID deletion exists exclusively for finally cleanup on failed probes.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {randomUUID,createHash} from 'node:crypto';import {tmpdir} from 'node:os';
import path from 'node:path';import {fileURLToPath} from 'node:url';
import {readCreateWorkerLog,readCreateReadiness,readyCreateView,controlPaintBox,headingPaintBox,controlTabletPoint,readyFilteredOwnList,assertRuntimeCreateAudit} from './tablet-create-readiness.mjs';
import {workerProfiles,freshWorkerProfile,readNativeSelection,assertOwnNativeSelection} from './tablet-create-selection.mjs';
import {assertIsolatedCreateTarget,baselineIdentity,assertBaseline,discoverOwnedShape,assertExpectedShape} from './tablet-create-contract.mjs';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..'),client=path.join(repo,'browser-client'),lab=path.join(repo,'build/browser-lab');
const runID=randomUUID(),name='Native Create Fixture '+runID,base=process.env.OVERTE_LAB_URL||'http://127.0.0.1:8090',domain='overte://127.0.0.2:45102';assertIsolatedCreateTarget(base,domain);
const discovery=process.env.OVERTE_CREATE_DISCOVERY==='1';
// Editable coordinates always come from the fixed read-only audit of the
// actually drawn native capture, including responsive layouts. No guessed map.
const directory=path.join(lab,'evidence/tablet-create',runID),profile=path.join(directory,'profile'),httpDirectory=path.join(lab,'http/create-fixtures',runID),assetBase=`http://127.0.0.1:45110/create-fixtures/${runID}/`;
const sha=data=>createHash('sha256').update(data).digest('hex'),delay=ms=>new Promise(r=>setTimeout(r,ms));
const sources=['tests/integration/tablet-create.mjs','tests/integration/tablet-create-readiness.mjs','tests/integration/tablet-create-contract.mjs','tests/integration/tablet-create-selection.mjs','tests/integration/native-create-observer.js','tests/integration/system-firefox.mjs','gateway/native-tablet.js','gateway/tablet-capture.qml','gateway/native-bridge.js','gateway/create-responsive-overrides.mjs','src/world.ts','src/session.ts'];
async function hashes(){return Object.fromEntries(await Promise.all(sources.map(async file=>[file,sha(await readFile(path.join(client,file)))])));}
const report={startedAt:new Date().toISOString(),completed:false,functionalAcceptance:false,discovery,scope:'Genuine native Qt Create on the isolated seven-entity local domain. No public writes, audio, direct property edits or scene provisioning.',screens:[],assertions:[],cleanupVerified:false};
let browser,page,native,log='',sequence=1,baseline,owned,guiDeleted=false,workerProfile;
function records(){return log.split('\n').filter(line=>line.includes('NATIVE_CREATE_OBSERVER ')).map(line=>{try{return JSON.parse(line.split('NATIVE_CREATE_OBSERVER ')[1]);}catch{return null;}}).filter(Boolean);}
function latestSnapshot(){return records().filter(r=>r.kind==='snapshot').at(-1)?.data;}
async function waitFor(fn,label,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){if(native&&(native.exitCode!==null||native.signalCode!==null))throw Error('The independent native observer exited');const refused=records().find(r=>r.kind==='refused');if(refused)throw Error(refused.data.message);const value=await fn();if(value)return value;await delay(100);}throw Error(`${label} exceeded ${timeout} milliseconds`);}
async function command(action){const current=sequence++;await writeFile(path.join(httpDirectory,'command.json'),JSON.stringify({sequence:current,action})+'\n');return current;}
async function stop(child){if(!child||child.exitCode!==null||child.signalCode!==null)return;child.kill('SIGTERM');await Promise.race([new Promise(r=>child.once('exit',r)),delay(2500)]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await Promise.race([new Promise(r=>child.once('exit',r)),delay(2500)]);}}
try{
 await mkdir(httpDirectory,{recursive:true});await mkdir(path.join(profile,'config/Overte'),{recursive:true});report.sourceHashes={start:await hashes()};
 const nativeRoot=path.join(lab,'appimage/squashfs-root');report.nativeBinarySHA256=sha(await readFile(path.join(nativeRoot,'usr/bin/interface')));assert.equal(report.nativeBinarySHA256,'91f3e10c42c1e35d5c8265e9b0007e925844d9bee61a26807118dde6e527887c','The independently audited native release must be unchanged');
 const nativeScripts=['system/create/qml/EditTabView.qml','system/create/entityProperties/html/js/entityProperties.js','system/create/entityList/html/js/entityList.js','system/create/edit.js'];report.nativeCreateScriptsSHA256=Object.fromEntries(await Promise.all(nativeScripts.map(async p=>[p,sha(await readFile(path.join(nativeRoot,'usr/bin/scripts',p)))])));
 await writeFile(path.join(profile,'config/Overte/Interface.json'),JSON.stringify({'Audio/mutedDesktop':true,'Audio/mutedHMD':true,'Audio/Desktop/INPUT':'lab_input.monitor','Audio/Desktop/OUTPUT':'lab_output'}));
 await writeFile(path.join(httpDirectory,'command.json'),'{}');const script=Buffer.concat([Buffer.from('var NATIVE_CREATE_OBSERVER='+JSON.stringify({name,commandURL:assetBase+'command.json'})+';\n'),await readFile(path.join(client,'tests/integration/native-create-observer.js'))]);await writeFile(path.join(httpDirectory,'observer.js'),script);report.observerScriptSHA256=sha(script);
 native=spawn(path.join(nativeRoot,'AppRun'),['--url',domain.replace('overte:','hifi:'),'--allowMultipleInstances','--no-updater','--no-login-suggestion','--suppress-settings-reset','--disableDisplayPlugins','OpenXR,OpenVR','--defaultScriptsOverride',assetBase+'observer.js'],{env:{...process.env,DISPLAY:':95',QT_QPA_PLATFORM:'xcb',QT_SCALE_FACTOR:'1',QT_AUTO_SCREEN_SCALE_FACTOR:'0',PULSE_SERVER:`unix:${lab}/runtime/native-pulse.sock`,XDG_CONFIG_HOME:path.join(profile,'config'),XDG_CACHE_HOME:path.join(profile,'cache'),XDG_DATA_HOME:path.join(profile,'data')},stdio:['ignore','pipe','pipe']});for(const stream of[native.stdout,native.stderr])stream.on('data',chunk=>{log=(log+chunk.toString()).slice(-4*1024*1024);});
 const ready=await waitFor(()=>{const x=latestSnapshot();return x?.entities.length===7?x:null;},'Independent native baseline',90000);baseline=baselineIdentity(ready.entities);assert.equal(ready.canRez,true,'Actual ordinary native guest must have rez permission');assert(String(ready.version).includes('2026.04.1'));report.nativeVersion=ready.version;report.baselineIdentitySHA256=sha(JSON.stringify(baseline));
 const display=process.env.OVERTE_LAB_BROWSER_DISPLAY,env={...process.env,...(display?{DISPLAY:display}:{})};
 if(process.env.OVERTE_LAB_BROWSER==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});else{assert(process.env.OVERTE_LAB_CHROMIUM,'A stock Chromium executable is required');browser=await chromium.launch({executablePath:process.env.OVERTE_LAB_CHROMIUM,headless:!display,env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=browser.version();const context=await browser.newContext({viewport:{width:1280,height:900}});page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message.slice(0,1024)));
 await page.addInitScript(()=>{const Original=window.WebSocket;window.__createAudit={entities:new Map(),frames:[],frame:null,states:[],warnings:[],tabletErrors:[]};window.WebSocket=class extends Original{constructor(...args){super(...args);this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{const m=JSON.parse(event.data),a=window.__createAudit;if(m.type==='entities')a.entities=new Map(m.entities.map(e=>[e.id,e]));if(m.type==='entityUpdates'){for(const id of m.removed)a.entities.delete(id);for(const e of m.entities)a.entities.set(e.id,e);}if(m.type==='warning'){a.warnings.push(m.message);if(a.warnings.length>16)a.warnings.shift();}if(m.type==='tablet'&&m.kind==='error'){a.tabletErrors.push(m.message);if(a.tabletErrors.length>16)a.tabletErrors.shift();}if(m.type==='tablet'&&m.kind==='frame'){a.frames.push(m);if(a.frames.length>8)a.frames.shift();}if(m.type==='tablet'&&m.kind==='state'){a.states.push({screen:m.screen,visible:m.visible});if(a.states.length>20)a.states.shift();}}catch{}});}send(data){if(typeof data==='string')try{const m=JSON.parse(data);if(m.type==='tablet'&&m.action==='frameAck'&&m.displayed===true){const a=window.__createAudit,f=a.frames.find(f=>f.sequence===m.frameSequence&&f.revision===m.revision);if(f)a.frame=f;}}catch{}super.send(data);}};});
 const profilesBefore=await workerProfiles(tmpdir());await page.goto(base);await page.locator('#domain').fill(domain);await page.locator('#name').fill('Native Create Browser Audit');await page.locator('#join').click();await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});
 workerProfile=freshWorkerProfile(profilesBefore,await workerProfiles(tmpdir()));report.runtimeAuditCaptureSHA256=await assertRuntimeCreateAudit(workerProfile,await readFile(path.join(client,'gateway/tablet-capture.qml'),'utf8'));const baselineGeometry=await page.evaluate(()=>window.__overte.performance.geometries);await page.locator('#tablet').click();await page.waitForFunction(()=>window.__createAudit.frame?.tabletRect,undefined,{timeout:30000});const canvas=page.getByLabel('Native tablet apps and dialogs');
 async function capture(label){const frame=await page.evaluate(()=>window.__createAudit.frame);assert(frame?.tabletRect);const bytes=Buffer.from(frame.data,'base64');await writeFile(path.join(directory,label+'-native.png'),bytes);const displayed=await canvas.evaluate(el=>el.toDataURL('image/png'));await writeFile(path.join(directory,label+'-displayed.png'),Buffer.from(displayed.split(',')[1],'base64'));report.screens.push({label,screen:await page.evaluate(()=>window.__createAudit.states.at(-1)?.screen),pngSHA256:sha(bytes),width:frame.width,height:frame.height,tabletRect:frame.tabletRect});return frame;}
 async function tap(x,y){const frame=await page.evaluate(()=>window.__createAudit.frame),r=frame.tabletRect,b=await canvas.boundingBox();assert(b&&r);await page.mouse.click(b.x+(r.x+x*r.width/480)/frame.width*b.width,b.y+(r.y+y*r.height/706)/frame.height*b.height);}
 async function updated(previous){await page.waitForFunction(p=>window.__createAudit.frame.sequence>p.sequence&&window.__createAudit.frame.data!==p.data,{sequence:previous.sequence,data:previous.data},{timeout:20000});}
 async function readyNativeView(route,section){let stable=null;
  let last=null;
  try{return await waitFor(async()=>{
   const frame=await page.evaluate(()=>window.__createAudit.frame);if(!frame)return null;
   const records=await readCreateReadiness(workerProfile);last=records.at(-1)||last;
   const entry=readyCreateView(records,frame,route,owned.id,section);if(!entry){stable=null;return null;}
   const control=route==='properties'?(section&&section!=='base'?'section-title':'property-id'):'filter-search',box=control==='section-title'?headingPaintBox(entry,frame):controlPaintBox(entry,control,frame);
   // UUID text (base), the native section heading, or Search (List) must actually
   // be rasterized. Ignore control borders and uniform gray skeleton blocks.
   const paint=await canvas.evaluate((el,box)=>{
    const sx=el.width/window.__createAudit.frame.width,sy=el.height/window.__createAudit.frame.height;
    const x=Math.ceil((box.x+3)*sx),y=Math.ceil((box.y+3)*sy),w=Math.floor((box.width-6)*sx),h=Math.floor((box.height-6)*sy);
    if(w<1||h<1||w*h>524288)return null;
    const p=el.getContext('2d').getImageData(x,y,w,h).data;let dark=0,ink=0;
    for(let i=0;i<p.length;i+=4){const b=Math.min(p[i],p[i+1],p[i+2]);if(b<90)dark++;if(b>140&&b<240)ink++;}
    return {dark,ink};
   },box);
   if(!paint||paint.dark<50||paint.ink<20){stable=null;return null;}
   if(section){const old=stable;stable={sequence:frame.sequence,revision:frame.revision,data:frame.data};if(!old||old.sequence>=frame.sequence||old.revision!==frame.revision||old.data!==frame.data)return null;}
   const current=await page.evaluate(()=>window.__createAudit.frame);
   if(current.sequence!==frame.sequence||current.revision!==frame.revision)return null;
   report.nativeReadiness||=[];report.nativeReadiness.push({route,section:entry.dom.section,colorPickerActive:entry.dom.colorPickerActive,controls:entry.dom.controls,web:entry.web,viewport:entry.dom.viewport,sequence:entry.sequence,revision:entry.revision,fontsStatus:entry.dom.fontsStatus,fonts:entry.dom.fonts,requiredFonts:entry.dom.requiredFonts,labelCount:entry.dom.labelCount,rowCount:entry.dom.rowCount,controlPaint:paint});
   return frame;
  },'Actual native '+route+' '+(section||'')+' route, initialized controls, font completion and text pixels',30000);}
  catch(error){report.lastNativeReadiness=last?{sequence:last.sequence,revision:last.revision,route:last.dom.route,section:last.dom.section,colorPickerActive:last.dom.colorPickerActive,readyState:last.dom.readyState,eventBridge:last.dom.eventBridge,fontsStatus:last.dom.fontsStatus,fonts:last.dom.fonts,requiredFonts:last.dom.requiredFonts,labelCount:last.dom.labelCount,rowCount:last.dom.rowCount,controls:last.dom.controls,web:last.web}:null;throw error;}
 }
 async function currentControl(id,route='properties',section){return await waitFor(async()=>{
  const frame=await page.evaluate(()=>window.__createAudit.frame);if(!frame)return null;
  const entry=readyCreateView(await readCreateReadiness(workerProfile),frame,route,owned.id,section);if(!entry)return null;
  const point=controlTabletPoint(entry,id,frame),current=await page.evaluate(()=>window.__createAudit.frame);
  if(current.sequence!==frame.sequence||current.revision!==frame.revision)return null;return point;
 },'Current displayed native '+id+' geometry',10000);}
 async function tapControl(id,route='properties',section){await tap(...await currentControl(id,route,section));}
 async function inputControl(id,text,route='properties',section){await tapControl(id,route,section);await page.keyboard.press('Control+a');await page.getByLabel('Native tablet text input').evaluate((el,data)=>el.dispatchEvent(new CompositionEvent('compositionend',{data,bubbles:true})),String(text));
  // List refresh is genuinely wired to keyup/search, not input/change. Enter
  // must occur while its search field still owns native focus, before Tab.
  if(route==='list')await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');await delay(500);
 }
 async function filteredOwnRow(){return await waitFor(async()=>{
  const frame=await page.evaluate(()=>window.__createAudit.frame);if(!frame)return null;
  const entry=readyFilteredOwnList(await readCreateReadiness(workerProfile),frame,owned.id);if(!entry)return null;
  const current=await page.evaluate(()=>window.__createAudit.frame);if(current.sequence!==frame.sequence||current.revision!==frame.revision)return null;
  report.filteredList={visibleEntityCount:entry.dom.visibleEntityCount,ownEntitySHA256:sha(owned.id),sequence:frame.sequence,revision:frame.revision};return entry.ownRowPoint;
 },'Genuine List Enter refresh to the exact single own UUID',20000);}

 const home=await page.evaluate(()=>window.__createAudit.frame);await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForFunction(s=>window.__createAudit.frame.sequence>s&&window.__createAudit.states.at(-1)?.screen==='Home',home.sequence,{timeout:20000});await capture('home');
 let previous=await page.evaluate(()=>window.__createAudit.frame);await tap(240,460);await updated(previous);await capture('create');
 await command('arm');await waitFor(()=>records().find(r=>r.kind==='armed'),'Native single-attempt ownership latch',10000);
 previous=await page.evaluate(()=>window.__createAudit.frame);await tap(200,160);await updated(previous);await waitFor(()=>records().find(r=>r.kind==='owned'),'Native observation of the genuine Shape rez',20000);owned=discoverOwnedShape(ready.entities,latestSnapshot().entities);report.ownedEntitySHA256=sha(owned.id);report.ownedFixtureCount=1;await readyNativeView('properties');await capture('properties-initial');
 await page.waitForFunction(id=>['Shape','Box'].includes(window.__createAudit.entities.get(id)?.type)&&window.__createAudit.entities.get(id)?.shape==='Cube'&&window.__overte.performance.geometries>0,owned.id,{timeout:20000});report.geometryDiagnostic={before:baselineGeometry,after:await page.evaluate(()=>window.__overte.performance.geometries)};report.assertions.push('Native Shape button created exactly one domain Cube and its actual domain properties reached the browser');
 if(discovery){
  await readyNativeView('properties','base');
  previous=await page.evaluate(()=>window.__createAudit.frame);await tapControl('tab-shape','properties','base');await updated(previous);await readyNativeView('properties','shape');await capture('shape-properties-calibration');
  const swatchPoint=await currentControl('property-color','properties','shape');report.colorSwatchPoint=swatchPoint;
  previous=await page.evaluate(()=>window.__createAudit.frame);await tap(...swatchPoint);await updated(previous);await readyNativeView('properties','colorPicker');await capture('color-picker-calibration');
  // Close through the currently captured native Shape tab, never a guessed
  // coordinate or a direct colpick/DOM call.
  await tapControl('tab-shape','properties','shape');
  previous=await page.evaluate(()=>window.__createAudit.frame);await tapControl('tab-spatial','properties','shape');await updated(previous);await readyNativeView('properties','spatial');await capture('transform-properties-calibration');
  previous=await page.evaluate(()=>window.__createAudit.frame);await tap(144,20);await updated(previous);await readyNativeView('list');await capture('list-initial');report.completed=true;report.functionalAcceptance=false;report.next='Inspect the native Properties/List captures; functional input uses their fixed read-only control geometry, and discovery deliberately does not claim edits/deletion';}
 else{
  await inputControl('property-name',name,'properties','base');await waitFor(()=>latestSnapshot().entities.find(e=>e.id===owned.id)?.name===name,'Genuine native Name edit',20000);
  previous=await page.evaluate(()=>window.__createAudit.frame);await tapControl('tab-shape','properties','base');await updated(previous);await readyNativeView('properties','shape');await capture('shape-properties');
  previous=await page.evaluate(()=>window.__createAudit.frame);await tapControl('property-color','properties','shape');await updated(previous);await readyNativeView('properties','colorPicker');await capture('color-picker-edit');
  const color={red:30,green:170,blue:220},dimensions={x:.7,y:.9,z:1.1};for(const channel of ['red','green','blue'])await inputControl('picker-'+channel,color[channel],'properties','colorPicker');
  await tap(...await currentControl('tab-shape','properties','shape'));previous=await page.evaluate(()=>window.__createAudit.frame);await tapControl('tab-spatial','properties','shape');await updated(previous);await readyNativeView('properties','spatial');await capture('transform-properties');for(const axis of ['x','y','z'])await inputControl('property-localDimensions-'+axis,dimensions[axis],'properties','spatial');
  const expected={id:owned.id,name,color,dimensions};const finalNative=await waitFor(()=>{const e=latestSnapshot().entities.find(e=>e.id===owned.id);try{assertExpectedShape(e,expected);return e;}catch{return null;}},'Actual native Name/Color/Dimensions',20000);
  await page.waitForFunction(expected=>{const e=window.__createAudit.entities.get(expected.id);return e?.name===expected.name&&Object.keys(expected.color).every(k=>e.color?.[k]===expected.color[k])&&Object.keys(expected.dimensions).every(k=>Math.abs(e.dimensions?.[k]-expected.dimensions[k])<.0001);},expected,{timeout:20000});assertExpectedShape(await page.evaluate(id=>window.__createAudit.entities.get(id),owned.id),expected);assertBaseline(latestSnapshot().entities,baseline);report.editedProperties={nameSHA256:sha(name),color:finalNative.color,dimensions:finalNative.dimensions};await capture('properties-edited');
  previous=await page.evaluate(()=>window.__createAudit.frame);await tap(144,20);await updated(previous);await readyNativeView('list');await inputControl('filter-search',name,'list');const ownRowPoint=await filteredOwnRow();await capture('list-filtered-before-selection');const previousSelection=await readNativeSelection(workerProfile);await tap(...ownRowPoint);await waitFor(async()=>{const trace=await readNativeSelection(workerProfile);try{assertOwnNativeSelection(trace,previousSelection.count,owned.id);return trace;}catch{return null;}},'Actual native single own selection from genuine List row',10000);await capture('list-selected-owned');
  // A second filter match would make deletion ambiguous; the independent native
  // observation must still contain exactly one matching own Cube and no children.
  assert.equal(latestSnapshot().entities.filter(e=>e.name===name).length,1);assert.equal(latestSnapshot().entities.find(e=>e.id===owned.id)?.children.length,0,'List deletion must not recursively delete attached children');assertExpectedShape(latestSnapshot().entities.find(e=>e.id===owned.id),expected);
  assertOwnNativeSelection(await readNativeSelection(workerProfile),previousSelection.count,owned.id);await filteredOwnRow();await tapControl('delete','list');await waitFor(()=>!latestSnapshot().entities.some(e=>e.id===owned.id),'Actual native deletion from List UI',20000);await page.waitForFunction(id=>!window.__createAudit.entities.has(id),owned.id,{timeout:20000});guiDeleted=true;await capture('list-deleted');
  assertBaseline(latestSnapshot().entities,baseline);assert.equal(latestSnapshot().entities.length,7);report.geometryDiagnostic.afterDeletion=await page.evaluate(()=>window.__overte.performance.geometries);report.assertions.push('Genuine Qt Name/Color/Dimensions changes agree with independent native observation and browser domain data; List UI deletes the single own Shape');report.functionalAcceptance=true;report.completed=true;
 }
 assert.deepEqual(errors,[]);
}catch(error){
 report.error=String(error.message||error);report.completed=false;process.exitCode=1;
 // Preserve this exact owned worker before gateway teardown removes its profile.
 // Raw native logs stay private; the public report only records its digest.
 if(workerProfile)try{const bytes=await readCreateWorkerLog(workerProfile);await writeFile(path.join(directory,'worker-private.log'),bytes,{mode:0o600});report.workerPrivateLogSHA256=sha(bytes);}catch{report.workerLogAvailable=false;}
 if(page){report.tabletErrorMessages=await page.evaluate(()=>window.__createAudit?.tabletErrors||[]).catch(()=>[]);await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});}
}
finally{
 if(baseline&&native?.exitCode===null&&native.signalCode===null){try{
  if(!guiDeleted&&records().some(r=>r.kind==='armed')){await command('cleanup');const cleaned=await waitFor(()=>records().find(r=>r.kind==='cleanup-sent'),'Finally-only exact own-ID deletion',10000);const latch=records().find(r=>r.kind==='owned');if(!owned&&latch)owned={id:latch.data.id};report.ownedFixtureCount=Math.max(report.ownedFixtureCount||0,cleaned.data.ownedCount);report.emergencyCleanup=cleaned.data.ownedCount===1;}
  const remaining=await waitFor(()=>{const x=latestSnapshot();if(!x||owned&&x.entities.some(e=>e.id===owned.id))return null;assertBaseline(x.entities,baseline);return x.entities.length===7?x:null;},'Native exact baseline restoration',15000);assert.deepEqual(baselineIdentity(remaining.entities),baseline);report.cleanupVerified=true;
  if(page&&owned)await page.waitForFunction(id=>!window.__createAudit.entities.has(id),owned.id,{timeout:15000});
 }catch(e){report.cleanupError=e.message;report.completed=false;process.exitCode=1;}}
 if(owned&&!report.cleanupVerified){report.completed=false;process.exitCode=1;}
 if(page){try{await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected,undefined,{timeout:10000});}catch{}report.warningCount=await page.evaluate(()=>window.__createAudit?.warnings.length||0).catch(()=>null);}
 await stop(native);await browser?.close();await mkdir(directory,{recursive:true});await writeFile(path.join(directory,'native-private.log'),log,{mode:0o600});await rm(httpDirectory,{recursive:true,force:true});await rm(profile,{recursive:true,force:true});report.sourceHashes||={};report.sourceHashes.end=await hashes();report.sourceCoherent=JSON.stringify(report.sourceHashes.start)===JSON.stringify(report.sourceHashes.end);if(!report.sourceCoherent){report.completed=false;report.error||='Source changed during genuine Create proof';process.exitCode=1;}report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
