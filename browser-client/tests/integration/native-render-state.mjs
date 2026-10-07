// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real Model/Material entities, real f91 native snapshots and authenticated BrowserWorld pixels.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {deflateSync} from 'node:zlib';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const id=randomUUID(),prefix=`Native Render Fixture ${id} `;
const lab=path.join(repo,'build/browser-lab'),httpDirectory=path.join(lab,'http','render-fixtures',id);
const output=path.join(repo,'build/browser-lab/evidence','render-state',id),profile=path.join(output,'profile');
const origin='http://127.0.0.1:5173',domain='overte://127.0.0.2:45102';
const fixtureHTML=path.join(repo,'browser-client/build/native-render-state',id,'index.html');
const assetBase=`http://127.0.0.1:45110/render-fixtures/${id}/`;
const center={x:40,y:10,z:0},camera={x:40,y:10,z:4};
const report={startedAt:new Date().toISOString(),completed:false,scope:'Isolated local laboratory only; real Model/Material entities and real native/browser pixels',microphoneRequested:false,publicWorldWrites:0,cases:[],ownedFixtureCount:0};
const sourceFiles=['browser-client/tests/integration/native-render-state.mjs','browser-client/tests/integration/native-render-fixture.js','browser-client/tests/integration/system-firefox.mjs','browser-client/src/world.ts','browser-client/src/native-render-state.ts','browser-client/src/native-alpha-material.ts'];
async function sourceHashes(){const hashes={};for(const file of sourceFiles){try{hashes[file]=sha(await readFile(path.join(repo,file)));}catch{hashes[file]=null;}}return hashes;}
let browser,page,native,vite,log='',sequence=1,preservedBaseline;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
async function waitFor(fn,label,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){const value=await fn();if(value)return value;await delay(100);}throw Error(`${label} exceeded ${timeout} milliseconds`);}
function records(){return log.split('\n').filter(x=>x.includes('NATIVE_RENDER_FIXTURE ')).map(x=>{try{return JSON.parse(x.split('NATIVE_RENDER_FIXTURE ')[1]);}catch{return null;}}).filter(Boolean);}
async function command(action){const current=sequence++;await writeFile(path.join(httpDirectory,'command.json'),JSON.stringify({sequence:current,...action})+'\n');return current;}
// One mesh, one material, authored front triangle FIRST, reverse-wound farther triangle SECOND.
function gltf(){
 const positions=new Float32Array([-1,-1,.1,1,-1,.1,0,1,.1,-1,-1,0,0,1,0,1,-1,0]);
 const colors=new Float32Array([1,0,0,1,0,0,1,0,0,0,1,0,0,1,0,0,1,0]);
 const uvs=new Float32Array(Array.from({length:12},()=>.5)),indices=new Uint16Array([0,1,2,3,4,5]);
 const bytes=Buffer.concat([Buffer.from(positions.buffer),Buffer.from(colors.buffer),Buffer.from(uvs.buffer),Buffer.from(indices.buffer)]);
 return {asset:{version:'2.0'},extensionsUsed:['KHR_materials_unlit'],scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0,COLOR_0:1,TEXCOORD_0:2},indices:3,material:0}]}],materials:[{extensions:{KHR_materials_unlit:{}},doubleSided:true,alphaMode:'BLEND',pbrMetallicRoughness:{baseColorFactor:[1,1,1,.5],metallicFactor:0,roughnessFactor:1}}],buffers:[{uri:'data:application/octet-stream;base64,'+bytes.toString('base64'),byteLength:bytes.length}],bufferViews:[{buffer:0,byteOffset:0,byteLength:positions.byteLength},{buffer:0,byteOffset:positions.byteLength,byteLength:colors.byteLength},{buffer:0,byteOffset:positions.byteLength+colors.byteLength,byteLength:uvs.byteLength},{buffer:0,byteOffset:positions.byteLength+colors.byteLength+uvs.byteLength,byteLength:indices.byteLength}],accessors:[{bufferView:0,componentType:5126,count:6,type:'VEC3',min:[-1,-1,0],max:[1,1,.1]},{bufferView:1,componentType:5126,count:6,type:'VEC3'},{bufferView:2,componentType:5126,count:6,type:'VEC2'},{bufferView:3,componentType:5123,count:6,type:'SCALAR',min:[0],max:[5]}]};
}
function crc(bytes){let x=0xffffffff;for(const b of bytes){x^=b;for(let i=0;i<8;i++)x=(x>>>1)^((x&1)?0xedb88320:0);}return(x^0xffffffff)>>>0;}
function png(){const chunk=(name,data)=>{const kind=Buffer.from(name),length=Buffer.alloc(4),sum=Buffer.alloc(4);length.writeUInt32BE(data.length);sum.writeUInt32BE(crc(Buffer.concat([kind,data])));return Buffer.concat([length,kind,data,sum]);};const header=Buffer.alloc(13);header.writeUInt32BE(1,0);header.writeUInt32BE(1,4);header[8]=8;header[9]=6;return Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',header),chunk('IDAT',deflateSync(Buffer.from([0,255,255,255,255]))),chunk('IEND',Buffer.alloc(0))]);}
async function pixelSummary(bytes){return page.evaluate(async encoded=>{const image=new Image();image.src='data:image/png;base64,'+encoded;await image.decode();const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const x=Math.floor(canvas.width/2)-8,y=Math.floor(canvas.height/2)-8,data=ctx.getImageData(x,y,16,16).data,total=[0,0,0,0];for(let i=0;i<data.length;i++)total[i%4]+=data[i];return {width:canvas.width,height:canvas.height,region:{x,y,width:16,height:16},rgba:total.map(n=>n/256)};},bytes.toString('base64'));}
async function stop(child){if(!child||child.exitCode!==null)return;child.kill('SIGTERM');await Promise.race([new Promise(r=>child.once('exit',r)),delay(2500)]);if(child.exitCode===null){child.kill('SIGKILL');await Promise.race([new Promise(r=>child.once('exit',r)),delay(2500)]);}}
try{
 report.startSourceSHA256=await sourceHashes();report.nativeBinarySHA256=sha(await readFile(path.join(lab,'appimage/squashfs-root/usr/bin/interface')));
 await mkdir(path.dirname(fixtureHTML),{recursive:true});await writeFile(fixtureHTML,'<!doctype html><div id="world" style="width:1024px;height:768px"></div>');
 await mkdir(httpDirectory,{recursive:true});await mkdir(path.join(profile,'config/Overte'),{recursive:true});
 await writeFile(path.join(profile,'config/Overte/Interface.json'),JSON.stringify({'Audio/mutedDesktop':true,'Audio/mutedHMD':true,'Audio/Desktop/INPUT':'lab_input.monitor','Audio/Desktop/OUTPUT':'lab_output'}));
 const geometry=Buffer.from(JSON.stringify(gltf())),mask=png();await writeFile(path.join(httpDirectory,'triangles.gltf'),geometry);await writeFile(path.join(httpDirectory,'mask.png'),mask);await writeFile(path.join(httpDirectory,'command.json'),'{}');
 const config={prefix,center,camera,outputDirectory:output,modelURL:assetBase+'triangles.gltf',maskURL:assetBase+'mask.png',commandURL:assetBase+'command.json'};
 const script=Buffer.concat([Buffer.from('var NATIVE_RENDER_FIXTURE='+JSON.stringify(config)+';\n'),await readFile(path.join(repo,'browser-client/tests/integration/native-render-fixture.js'))]);await writeFile(path.join(httpDirectory,'author.js'),script);
 report.generatedAssetSHA256={gltf:sha(geometry),mask:sha(mask),nativeScript:sha(script)};
 // Refuse an occupied test server; do not replace an unrelated Vite process.
 try{await fetch(origin,{signal:AbortSignal.timeout(300)});throw Error('Render fixture Vite port is already occupied');}catch(e){if(e.message==='Render fixture Vite port is already occupied')throw e;}
 vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort'],{cwd:path.join(repo,'browser-client'),stdio:'ignore'});
 await waitFor(async()=>{try{return(await fetch(origin)).ok;}catch{return false;}},'Owned Vite startup',10000);
 const nativeEnv={...process.env,DISPLAY:':95',QT_QPA_PLATFORM:'xcb',QT_SCALE_FACTOR:'1',QT_AUTO_SCREEN_SCALE_FACTOR:'0',PULSE_SERVER:`unix:${lab}/runtime/native-pulse.sock`,XDG_CONFIG_HOME:path.join(profile,'config'),XDG_CACHE_HOME:path.join(profile,'cache'),XDG_DATA_HOME:path.join(profile,'data')};
 native=spawn(path.join(lab,'appimage/squashfs-root/AppRun'),['--url',domain.replace('overte:','hifi:'),'--allowMultipleInstances','--no-updater','--no-login-suggestion','--suppress-settings-reset','--disableDisplayPlugins','OpenXR,OpenVR','--defaultScriptsOverride',assetBase+'author.js'],{env:nativeEnv,stdio:['ignore','pipe','pipe']});
 for(const stream of [native.stdout,native.stderr])stream.on('data',chunk=>{log=(log+chunk.toString()).slice(-2*1024*1024);});
 native.once('exit',(code,signal)=>{report.nativeExit={code,signal};});
 const created=await waitFor(()=>records().find(x=>x.kind==='created'),'Native real fixture creation (guest must actually canRez)',90000);report.nativeVersion=created.data.version;report.ownedFixtureCount=created.data.ownedCount;assert(String(report.nativeVersion).includes('2026.04.1'),'Reference native must be the pinned f91 release');
 const display=process.env.OVERTE_LAB_BROWSER_DISPLAY,env={...process.env,...(display?{DISPLAY:display}:{})};
 if(process.env.OVERTE_LAB_BROWSER==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});
 else browser=await chromium.launch({headless:!display,executablePath:process.env.OVERTE_LAB_CHROMIUM,env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:[...(!display?['--use-angle=swiftshader']:[]),'--mute-audio']});
 report.browserVersion=await browser.version();report.browserWindowViewport=process.env.OVERTE_LAB_BROWSER==='system-firefox'?{width:1280,height:800}:{width:1024,height:768};const context=await browser.newContext({viewport:report.browserWindowViewport});page=await context.newPage();await page.goto(origin+`/build/native-render-state/${id}/index.html`);
 await page.evaluate(async({prefix,domain,camera})=>{
  const {BrowserWorld}=await import('/src/world.ts'),{BrowserSession}=await import('/src/session.ts'),THREE=await import('/node_modules/three/build/three.module.js');
  const fixture={entities:new Map(),errors:[],connected:false,world:null,session:null,positioning:null};window.__nativeRenderFixture=fixture;
  const render=()=>{fixture.world.setEntities([...fixture.entities.values()].filter(e=>e.name?.startsWith(prefix)));};
  const session=new BrowserSession({audio(){},closed(reason){fixture.connected=false;fixture.errors.push(reason);},error(reason){fixture.errors.push(reason);},message(m){if(m.type==='state'){fixture.connected=m.state==='connected';if(m.state==='error')fixture.errors.push(m.message);}if(m.type==='poseRequest')session.send({type:'poseAccepted',nonce:m.nonce,permissionRevision:m.permissionRevision});if(m.type==='entities'){fixture.entities=new Map(m.entities.map(e=>[e.id,e]));render();}if(m.type==='entityUpdates'){for(const id of m.removed)fixture.entities.delete(id);for(const e of m.entities)fixture.entities.set(e.id,e);render();}}});
  const world=new BrowserWorld(document.querySelector('#world'),{resolveAsset:url=>session.assetURL(url),onPose(){},onInteract(){},onStatus(message,kind){if(kind==='error'||kind==='warning')fixture.errors.push(message);}});fixture.world=world;fixture.session=session;fixture.THREE=THREE;
  const bootstrap=await fetch('/api/session',{credentials:'same-origin'});if(!bootstrap.ok)throw Error('Actual visitor session bootstrap failed');session.join(domain,'Native-render-pixel-fixture');
  // Normal authenticated visitor poses also position the native entity query.
  // A 512 m findEntities call can only search the octree already streamed for
  // this camera; it does not fetch an off-frustum diagnostic fixture by itself.
  fixture.positioning=setInterval(()=>{if(fixture.connected)session.sendPose({position:camera,orientation:{x:0,y:0,z:0,w:1},velocity:{x:0,y:0,z:0}});},200);
 },{prefix,domain,camera});
 await waitFor(async()=>{if(native.exitCode!==null||native.signalCode!==null)throw Error('Actual native observer exited before model/render readiness: '+JSON.stringify(report.nativeExit));const nativeReady=records().find(x=>x.kind==='native-ready');if(!nativeReady)return false;const browserReady=await page.evaluate(()=>{const f=window.__nativeRenderFixture;return f.connected&&f.world.getPerformance().loadedModels===1&&f.world.getPerformance().loadingModels===0&&f.world.getPerformance().compilingGraphics===0;});if(browserReady)report.nativeReadiness=nativeReady;return browserReady;},'Authenticated actual browser/native model and render readiness',90000);
 preservedBaseline=await page.evaluate(()=>[...window.__nativeRenderFixture.entities.values()].filter(e=>e.name?.startsWith('Browser Lab ')).map(e=>e.id).sort());assert.equal(preservedBaseline.length,7,'Exactly seven existing laboratory entities must remain untouched');report.preservedBaselineCount=preservedBaseline.length;
 for(const [name,cull,mode,dominant] of [['no-cull-blend','CULL_NONE','blend','green'],['cull-back-blend','CULL_BACK','blend','red'],['cull-front-blend','CULL_FRONT','blend','green'],['no-cull-mask-depth','CULL_NONE','mask','red'],['no-cull-opaque-depth','CULL_NONE','opaque','red']]){
  const current=await command({action:'case',cull,mode});await waitFor(()=>records().find(x=>x.kind==='case-applied'&&x.data.sequence===current),'Actual native Material edit');
  await waitFor(()=>page.evaluate(({cull,mode})=>{const f=window.__nativeRenderFixture,e=[...f.entities.values()].find(e=>e.name?.endsWith('material')&&!e.name.endsWith('background-material'));if(!e)return false;const m=JSON.parse(e.materialData).materials;return m.cullFaceMode===cull&&m.opacity===(mode==='blend'?.5:1)&&f.world.getPerformance().compilingGraphics===0;},{cull,mode}),'Actual entity update at browser');await delay(2500);
  const snap=await command({action:'snapshot'}),entry=await waitFor(()=>{const failed=records().find(x=>x.kind==='snapshot-error'&&x.data.sequence===snap);if(failed)throw Error(failed.data.message);return records().find(x=>x.kind==='snapshot'&&x.data.sequence===snap);},'Native GPU snapshot',30000);
  const nativeDiagnostic=records().find(x=>x.kind==='snapshot-ready'&&x.data.sequence===snap)?.data.diagnostic;
  const nativePath=path.resolve(entry.data.filename);assert(nativePath.startsWith(output+path.sep),'Native snapshot must stay in owned output directory');const nativeBytes=await readFile(nativePath);
  const browserCapture=await page.evaluate(async({center,camera})=>{const f=window.__nativeRenderFixture,w=f.world,r=w.renderer,c=w.camera;r.setPixelRatio(1);r.setSize(1024,768);c.aspect=4/3;c.position.set(camera.x,camera.y,camera.z);c.lookAt(center.x,center.y,center.z);c.updateProjectionMatrix();r.render(w.scene,c);const png=w.canvas.toDataURL('image/png');const state=[];w.scene.traverse(o=>{if(o.isMesh&&o.geometry.getAttribute('position')?.count===6){const ms=Array.isArray(o.material)?o.material:[o.material];for(const m of ms)state.push({side:m.side,transparent:m.transparent,depthWrite:m.depthWrite,forceSinglePass:m.forceSinglePass,opacity:m.opacity});}});return {png,state,calls:r.info.render.calls};},{center,camera});
  const browserBytes=Buffer.from(browserCapture.png.split(',')[1],'base64');await writeFile(path.join(output,`${name}-browser.png`),browserBytes);await writeFile(path.join(output,`${name}-native.png`),nativeBytes);
  const nativePixels=await pixelSummary(nativeBytes),browserPixels=await pixelSummary(browserBytes),wanted=dominant==='red'?0:1,other=1-wanted;
  const result={name,cull,mode,nativeDiagnostic,nativePixels,browserPixels,browserMaterialStates:browserCapture.state,browserDrawCalls:browserCapture.calls,expectedDominant:dominant,nativePNG_SHA256:sha(nativeBytes),browserPNG_SHA256:sha(browserBytes)};report.cases.push(result);
  assert(nativePixels.rgba[wanted]>nativePixels.rgba[other]+15,`Actual native ${name} must be ${dominant}-dominant`);assert(browserPixels.rgba[wanted]>browserPixels.rgba[other]+15,`Actual browser ${name} must match native ${dominant} dominance`);
  assert(browserCapture.state.length>0,'Measured actual imported model material');for(const state of browserCapture.state){assert.equal(state.depthWrite,mode!=='blend');if(cull==='CULL_NONE')assert.equal(state.forceSinglePass,true);}
 }
 report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;if(page)try{report.failureDiagnostics=await page.evaluate(()=>{const f=window.__nativeRenderFixture;return f?{connected:f.connected,entityCount:f.entities.size,errors:f.errors.slice(-20),performance:f.world.getPerformance()}:null;});}catch{}}
finally{
 if(native?.exitCode===null){try{await command({action:'cleanup'});await waitFor(()=>records().find(x=>x.kind==='cleanup-sent'),'Owned native fixture cleanup',10000);report.cleanupRequested=true;if(page&&preservedBaseline){await waitFor(()=>page.evaluate(prefix=>[...window.__nativeRenderFixture.entities.values()].filter(e=>e.name?.startsWith(prefix)).length===0,prefix),'Actual gateway delivery of fixture deletion',15000);const remaining=await page.evaluate(()=>[...window.__nativeRenderFixture.entities.values()].filter(e=>e.name?.startsWith('Browser Lab ')).map(e=>e.id).sort());assert.deepEqual(remaining,preservedBaseline,'All seven pre-existing entities retain their exact identities');report.cleanupVerified=true;}}catch(e){report.cleanupError=e.message;report.completed=false;process.exitCode=1;}}
 if(page)try{await page.evaluate(()=>{clearInterval(window.__nativeRenderFixture?.positioning);window.__nativeRenderFixture?.session.leave();window.__nativeRenderFixture?.world.dispose();});}catch{}
 await stop(native);await browser?.close();await stop(vite);
 // Never touch unrelated lab assets or entity names. Native fixtures additionally expire after240s.
 await writeFile(path.join(output,'native-private.log'),log,{mode:0o600});await rm(httpDirectory,{recursive:true,force:true});await rm(profile,{recursive:true,force:true});await rm(path.dirname(fixtureHTML),{recursive:true,force:true});
 report.nativeDiagnostics=records().filter(x=>x.kind==='diagnostic').slice(-16).map(x=>({at:x.at,...x.data}));
 report.finishedAt=new Date().toISOString();report.sourceSHA256=await sourceHashes();report.sourceCoherent=JSON.stringify(report.startSourceSHA256)===JSON.stringify(report.sourceSHA256);if(!report.sourceCoherent){report.completed=false;report.error=report.error||'Source changed during the actual pixel proof';process.exitCode=1;}
 await mkdir(output,{recursive:true});await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
