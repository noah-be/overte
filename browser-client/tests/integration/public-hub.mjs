// SPDX-License-Identifier: Apache-2.0
// Actual public-world read-only, always-muted diagnostics and movement proof.
// Raw reports are ignored; publish only sanitized aggregates, never identities.
import { chromium } from '@playwright/test';
import { launchSystemFirefox } from './system-firefox.mjs';
import assert from 'node:assert/strict';
import {assessFluidPerformance} from '../../shared/fluid-performance.mjs';
import { mkdir, readFile, writeFile, readdir, readlink } from 'node:fs/promises';
import { assetCategory, assetCategoryTotals, assetSessionTotals, requireWorldLoadingReady } from './public-hub-metrics.mjs';
import { createHash } from 'node:crypto';
import {installHubUploadProfile} from './hub-upload-profile.mjs';
import {collectHubAsyncDrawCensus} from './hub-async-draw-census.mjs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const firefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const output=path.join(repo,'build/browser-hub-lab/browser',...(firefox?['system-firefox']:[]));
const sourceFiles=['browser-client/gateway/server.mjs','browser-client/gateway/native-bridge.js','browser-client/gateway/native-world.js','browser-client/gateway/socket-heartbeat.mjs','browser-client/gateway/public-places.mjs','browser-client/gateway/validation.mjs','browser-client/gateway/worker-sandbox.mjs','browser-client/gateway/network-sandbox.mjs','browser-client/gateway/network_udp.py','browser-client/gateway/native-tablet.js','browser-client/gateway/tablet-capture.qml','browser-client/gateway/process-lifecycle.mjs','browser-client/shared/fluid-performance.mjs','browser-client/gateway/session-assets.mjs','browser-client/gateway/asset-download.mjs','browser-client/src/main.ts', 'browser-client/src/session.ts', 'browser-client/src/compressed-color-session.ts', 'browser-client/src/native-compressed-color.ts', 'browser-client/src/color-texture-metadata.ts', 'browser-client/src/initial-surface-wait.ts', 'browser-client/src/mesh-collision.ts', 'browser-client/src/simulation-clock.ts','browser-client/src/world.ts','browser-client/src/world-draw-census.ts','browser-client/src/world-bitmap-upload.ts','browser-client/src/world-bitmap-bindings.ts','browser-client/src/fst-graph-cache.ts','browser-client/src/fst-texture-admission.ts','browser-client/src/compressed-color-capabilities.ts','browser-client/src/graphics-warmup.ts','browser-client/src/graphics-warmup-owner.ts','browser-client/src/gpu-time-observer.ts','browser-client/src/world-gpu-timing.ts','browser-client/src/world-image-cache.ts','browser-client/src/world-source-text-cache.ts','browser-client/src/embedded-fbx-images.ts','browser-client/src/embedded-content-counts.ts','browser-client/src/embedded-fbx-protocol.ts','browser-client/src/native-zero-lights.ts','browser-client/src/static-model-batch.ts','browser-client/src/native-render-state.ts','browser-client/src/native-alpha-material.ts','browser-client/src/model-resources.ts','browser-client/src/world-data.ts','browser-client/src/worker-task-yield.ts','browser-client/src/prepared-fbx-cache.ts','browser-client/src/model-load-scheduler.ts','browser-client/src/model-geometry-stage.ts','browser-client/src/model-fbx-pool.ts','browser-client/src/model-fbx-decoder.ts','browser-client/src/model-fbx-decoder-memory.ts','browser-client/src/model-fbx-worker.ts','browser-client/src/model-textures.ts','browser-client/src/texture-alpha.ts','browser-client/src/texture-alpha-worker.ts','browser-client/src/baked-fbx.ts','browser-client/src/baked-draco.ts','browser-client/src/baked-draco-legacy.ts','browser-client/dist/index.html','browser-client/tests/integration/system-firefox.mjs','browser-client/tests/integration/public-hub-metrics.mjs','browser-client/tests/integration/public-hub.mjs'];
sourceFiles.push('browser-client/src/world-texture-preparation.ts','browser-client/src/foreground-texture-plan.ts','browser-client/src/world-cpu-frame-timing.ts','browser-client/src/render-cpu-breakdown.ts','browser-client/tests/integration/hub-upload-profile.mjs');
sourceFiles.push('browser-client/src/static-model-matrices.ts','browser-client/src/native-image-material.ts','browser-client/src/native-image-effects.ts');
sourceFiles.push('browser-client/src/model-parse-turn.ts');
sourceFiles.push('browser-client/src/world-draw-census-async.ts','browser-client/tests/integration/hub-async-draw-census.mjs');
const report={startedAt:new Date().toISOString(),completed:false,place:'overte_hub',microphoneRequested:false,worldInteractionsSent:0};
const assetRequests = new Map(), assetStarts = new WeakMap();
// Native session IDs are private lookup keys only; reports contain ordinal1/2.
const assetSessionIDs = new Map(), sessionAssetRequests = new Map();
async function distributionManifest() {
  const root = path.join(repo, 'browser-client/dist'), manifest = {};
  async function scan(relative) {
    for (const entry of await readdir(path.join(root, relative), {withFileTypes:true})) {
      const name = path.posix.join(relative, entry.name);
      if (entry.isDirectory()) await scan(name);
      else if (entry.isFile() && /\.(?:js|css|wasm)$/.test(name)) {
        const bytes = await readFile(path.join(root, name));
        manifest[name] = {sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
      }
    }
  }
  await scan('');
  return Object.fromEntries(Object.entries(manifest).sort(([a],[b])=>a.localeCompare(b)));
}
async function ownedRuntimeHelpers() {
  const port = new URL(process.env.OVERTE_LAB_URL || 'http://127.0.0.1:8092').port;
  if (port !== '8095' && port !== '8090') return {};
  const managed = port === '8090';
  const saved = JSON.parse(await readFile(path.join(repo, managed ? 'build/browser-lab/runtime/processes.json' : 'build/browser-hub-lab/gateway8095/process.json'), 'utf8'));
  const state = managed ? saved.gateway : saved;
  if (!Number.isSafeInteger(state?.pid) || state.pid < 1) throw Error('Owned gateway process record is invalid.');
  if (managed) {
    const stat = await readFile(`/proc/${state.pid}/stat`, 'utf8');
    const ticks = stat.slice(stat.lastIndexOf(') ') + 2).split(/\s+/)[19];
    if (ticks !== String(state.startTicks)) throw Error('Owned gateway process identity changed.');
    const cwd = await readlink(`/proc/${state.pid}/cwd`);
    if (cwd !== repo && cwd !== path.join(repo,'browser-client')) throw Error('Owned gateway working directory changed.');
    const args = (await readFile(`/proc/${state.pid}/cmdline`, 'utf8')).split('\0').filter(Boolean);
    if (!args.includes(path.join(repo,'browser-client/gateway/server.mjs')) && !args.includes('gateway/server.mjs')) throw Error('Owned gateway executable changed.');
  }
  // Node uses the gateway's own TMPDIR/TMP/TEMP, which can differ from /tmp.
  // Read only those path fields internally; never publish its environment.
  const environment = (await readFile(`/proc/${state.pid}/environ`, 'utf8')).split('\0');
  const tempField = ['TMPDIR','TMP','TEMP'].map(key => environment.find(value => value.startsWith(key+'='))).find(value => value?.slice(value.indexOf('=')+1));
  const temporaryRoot = path.resolve(tempField ? tempField.slice(tempField.indexOf('=')+1) : '/tmp');
  const children = (await readFile(`/proc/${state.pid}/task/${state.pid}/children`, 'utf8')).trim().split(/\s+/);
  const folders = new Set();
  for (const child of children) { try {
    const args = (await readFile(`/proc/${child}/cmdline`, 'utf8')).split('\0');
    for (const argument of args.filter(value => path.isAbsolute(value))) {
      const relative = path.relative(temporaryRoot, argument), name = relative.split(path.sep)[0];
      if (/^overte-browser-[a-zA-Z0-9]{6}$/.test(name)) folders.add(path.join(temporaryRoot, name));
    }
  } catch {} }
  const hashes = {};
  for (const folder of folders) for (const file of ['native-tablet.js', 'tablet-capture.qml', 'bridge.js']) { try { hashes[file] = createHash('sha256').update(await readFile(path.join(folder, file))).digest('hex'); } catch {} }
  if (!hashes['bridge.js'] || !hashes['native-tablet.js'] || !hashes['tablet-capture.qml']) throw Error('Owned gateway session helper hashes are unavailable.');
  return hashes;
}
let browser,page,profiler;
async function screenshot(filename){
  if(firefox){await page.screenshot({path:path.join(output,filename),animations:'disabled',caret:'hide'});return;}
  const cdp=await page.context().newCDPSession(page);
  try{const capture=await cdp.send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false});await writeFile(path.join(output,filename),Buffer.from(capture.data,'base64'));}finally{await cdp.detach();}
}
try {
  await mkdir(output,{recursive:true});
  report.startSourceSHA256={};for(const file of sourceFiles){try{report.startSourceSHA256[file]=createHash('sha256').update(await readFile(path.join(repo,file))).digest('hex');}catch{}}
  report.startDistributionManifest=await distributionManifest();
  report.asyncDrawCensusRequested=process.env.OVERTE_LAB_ASYNC_DRAW_CENSUS==='1';
  if(report.asyncDrawCensusRequested)assert(report.startSourceSHA256['browser-client/src/world-draw-census-async.ts'],'Async census source hash must be available before the diagnostic journey');
  const env={...process.env,PULSE_SERVER:`unix:${repo}/build/browser-hub-lab/hub/pulse.socket`};
  if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)env.LD_LIBRARY_PATH=process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH;
  if(process.env.OVERTE_LAB_BROWSER_DISPLAY)env.DISPLAY=process.env.OVERTE_LAB_BROWSER_DISPLAY;
  const args=['--disable-dev-shm-usage','--mute-audio'];
  if(process.env.OVERTE_LAB_SWIFTSHADER==='1')args.push('--use-angle=swiftshader');
  browser=firefox?await launchSystemFirefox({executablePath:process.env.OVERTE_LAB_FIREFOX||'/usr/bin/firefox',env,headless:!process.env.OVERTE_LAB_BROWSER_DISPLAY,syntheticMicrophone:false}):await chromium.launch({headless:!process.env.OVERTE_LAB_BROWSER_DISPLAY,args,env,
    ...(process.env.OVERTE_LAB_CHROMIUM?{executablePath:process.env.OVERTE_LAB_CHROMIUM}:{})});
  report.browserVersion=await browser.version();
  page=firefox?await(await browser.newContext({viewport:{width:1280,height:800}})).newPage():await browser.newPage({viewport:{width:1280,height:800}});
  if(firefox)page.waitForTimeout=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
  const errors=[];page.on('pageerror',error=>errors.push(error.message));report.failedResources=[];page.on('response',response=>{if(response.status()>=400)report.failedResources.push({status:response.status(),url:response.url()});});page.on('requestfailed',request=>report.failedResources.push({url:request.url(),failure:request.failure()?.errorText}));
  report.uploadProfileRequested=process.env.OVERTE_LAB_UPLOAD_PROFILE==='1';
  if(report.uploadProfileRequested)await page.addInitScript(installHubUploadProfile);
  await page.addInitScript(()=>{
    window.__hubGLCalls={totals:{},slow:[],programs:{},shaders:{},shaderDetails:{},readiness:{}};
    const ids=new WeakMap();let nextID=0;
    const id=value=>{if(!value||typeof value!=='object')return null;if(!ids.has(value))ids.set(value,++nextID);return ids.get(value);};
    for(const name of ['getProgramInfoLog','getShaderInfoLog','getProgramParameter','getActiveUniform','getUniformLocation','linkProgram','compileShader','attachShader','shaderSource','useProgram','texImage2D','texSubImage2D','compressedTexImage2D','compressedTexSubImage2D','texStorage2D','generateMipmap','bufferData','bufferSubData']){
      const original=WebGL2RenderingContext.prototype[name];
      WebGL2RenderingContext.prototype[name]=function(...args){
        const started=performance.now();let result;
        try{result=Reflect.apply(original,this,args);return result;}
        finally{
          const elapsed=performance.now()-started;
          const key=name+(typeof args[1]==='number'?':'+args[1]:'');
          const stat=window.__hubGLCalls.totals[key]||={calls:0,totalMs:0,maxMs:0};
          stat.calls++;stat.totalMs+=elapsed;stat.maxMs=Math.max(stat.maxMs,elapsed);
          // Observe only arguments already submitted by the application. Never
          // query driver state or let optional diagnostics change its result.
          if(name==='texImage2D'||name==='texSubImage2D'||name==='compressedTexImage2D'||name==='compressedTexSubImage2D'){
            try{window.__hubUploadProfile?.record(name,args,elapsed);}catch{}
          }
          if(name==='compressedTexImage2D'||name==='compressedTexSubImage2D'){
            const bytes=args.find(value=>ArrayBuffer.isView(value)||value instanceof ArrayBuffer);
            if(bytes)stat.uploadBytes=(stat.uploadBytes||0)+bytes.byteLength;
          }
          if(elapsed>50&&window.__hubGLCalls.slow.length<256){
            const image=args.find(value=>value&&typeof value==='object'&&typeof value.width==='number'&&typeof value.height==='number');
            const buffer=args.find(value=>ArrayBuffer.isView(value)||value instanceof ArrayBuffer);
            window.__hubGLCalls.slow.push({at:performance.now(),name,program:id(args[0]),parameter:typeof args[1]==='number'?args[1]:undefined,elapsed,lastReadiness:window.__hubGLCalls.readiness[id(args[0])],
              ...(image?{imageDimensions:{width:image.width,height:image.height}}:{}),...(buffer?{uploadBytes:buffer.byteLength}:{})});
          }
          // Observe only the application's existing completion queries: no new driver work.
          if(name==='getProgramParameter'&&args[1]===37297)window.__hubGLCalls.readiness[id(args[0])]={at:performance.now(),complete:result===true};
          if(name==='attachShader'){const program=window.__hubGLCalls.programs[id(args[0])]||=[];program.push(id(args[1]));}
          if(name==='shaderSource'){
            const source=String(args[1]);const shader=id(args[0]);
            window.__hubGLCalls.shaders[shader]=source.split('\n').filter(line=>line.startsWith('#define')).slice(0,100);
            const details={length:source.length,lightArrays:[...source.matchAll(/uniform\s+\w+\s+(\w*[Ll]ights)\s*\[\s*(\d+)\s*\]/g)].map(match=>({name:match[1],count:Number(match[2])}))};
            window.__hubGLCalls.shaderDetails[shader]=details;
            crypto.subtle.digest('SHA-256',new TextEncoder().encode(source)).then(bytes=>{details.sha256=[...new Uint8Array(bytes)].map(value=>value.toString(16).padStart(2,'0')).join('');});
          }
        }
      };
    }
    window.__hubLongTasks=[];new PerformanceObserver(list=>{for(const entry of list.getEntries())window.__hubLongTasks.push({start:entry.startTime,duration:entry.duration});if(window.__hubLongTasks.length>1000)window.__hubLongTasks.splice(0,window.__hubLongTasks.length-1000);}).observe({type:'longtask',buffered:true});window.__hubMessages=[];window.__hubEntitySummary=new Map();window.__hubNativePose=null;window.__hubTraffic={messages:0,textBytes:0,snapshots:0,deltas:0};const WS=window.WebSocket;window.WebSocket=class extends WS{constructor(...args){super(...args);this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{const j=JSON.parse(event.data);window.__hubTraffic.messages++;window.__hubTraffic.textBytes+=event.data.length;if(j.type==='entities'){window.__hubTraffic.snapshots++;window.__hubEntitySummary.clear();}if(j.type==='entityUpdates')window.__hubTraffic.deltas++;for(const entity of j.entities||[]){window.__hubEntitySummary.set(entity.id,{type:entity.type,hostType:entity.entityHostType||'missing',clientOnly:entity.clientOnly===true});}for(const id of j.removed||[])window.__hubEntitySummary.delete(id);if(j.type==='avatars'){const own=j.avatars.find(a=>a.id===j.selfId);if(own)window.__hubNativePose={at:Date.now(),position:own.position};}window.__hubMessages.push({at:Date.now(),type:j.type,state:j.state,message:j.message,position:j.position,entityCount:j.entities?.length});if(window.__hubMessages.length>100)window.__hubMessages.shift();}catch{}});this.addEventListener('close',event=>{window.__hubMessages.push({at:Date.now(),type:'close',code:event.code,reason:event.reason});});}};});
  const entryURL = new URL(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8092');
  if (process.env.OVERTE_LAB_GPU_TIMING === '1') entryURL.searchParams.set('gpuTiming','1');
  report.gpuTimingRequested = process.env.OVERTE_LAB_GPU_TIMING === '1';
  report.cpuFrameTimingRequested=process.env.OVERTE_LAB_CPU_FRAME_TIMING==='1';
  if(report.cpuFrameTimingRequested)entryURL.searchParams.set('cpuFrameTiming','1');
  report.renderCpuTimingRequested=process.env.OVERTE_LAB_RENDER_CPU_TIMING==='1';
  if(report.renderCpuTimingRequested)entryURL.searchParams.set('renderCpuTiming','1');
  report.staticModelMatricesRequested=process.env.OVERTE_LAB_STATIC_MODEL_MATRICES==='1';
  if(report.staticModelMatricesRequested)entryURL.searchParams.set('staticModelMatrices','1');
  report.bitmapUploadRequested=process.env.OVERTE_LAB_BITMAP_UPLOAD==='1';
  if(report.bitmapUploadRequested)entryURL.searchParams.set('bitmapUpload','1');
  report.modelParseTurnRequested=process.env.OVERTE_LAB_MODEL_PARSE_TURN==='1';
  if(report.modelParseTurnRequested)entryURL.searchParams.set('modelParseTurn','1');
  if (process.env.OVERTE_LAB_SHADER_WARMUP === '1') entryURL.searchParams.set('shaderWarmup','1');
  report.shaderWarmupRequested = process.env.OVERTE_LAB_SHADER_WARMUP === '1';
  if (process.env.OVERTE_LAB_TEXTURE_PREPARATION === '1') entryURL.searchParams.set('texturePreparation','1');
  report.texturePreparationRequested = process.env.OVERTE_LAB_TEXTURE_PREPARATION === '1';
  await page.goto(entryURL.href);
  report.viewport=await page.evaluate(()=>({width:innerWidth,height:innerHeight,devicePixelRatio,visibility:document.visibilityState}));
  await page.locator('#domain').fill('overte://overte_hub');
  page.on('request',request=>{if(request.url().includes('/api/assets/'))assetStarts.set(request,performance.now());});
  page.on('requestfinished',async request=>{
    if(!assetStarts.has(request))return;
    const requestURL=new URL(request.url()),original=requestURL.searchParams.get('url')||request.url();
    let ordinal=assetSessionIDs.get(requestURL.pathname);
    if(!ordinal){ordinal=assetSessionIDs.size+1;assetSessionIDs.set(requestURL.pathname,ordinal);}
    const key=createHash('sha256').update(original).digest('hex');
    const response=await request.response(),headers=response?.headers()||{},size=Number(headers['content-length']);
    const previous=assetRequests.get(key)||{category:assetCategory(original),requests:0,knownBytes:0,unknownByteResponses:0,totalMs:0,maximumMs:0,sources:{download:0,shared:0,memory:0,unknown:0}};
    const sessionKey=ordinal+':'+key;
    const sessionPrevious=sessionAssetRequests.get(sessionKey)||{ordinal,urlSHA256:key,category:assetCategory(original),requests:0,knownBytes:0,unknownByteResponses:0,totalMs:0,maximumMs:0,sources:{download:0,shared:0,memory:0,unknown:0}};
    const elapsed=performance.now()-assetStarts.get(request);
    for(const entry of [previous,sessionPrevious]){
      entry.requests++;entry.totalMs+=elapsed;entry.maximumMs=Math.max(entry.maximumMs,elapsed);
      const source=headers['x-overte-asset-source'];entry.sources[['download','shared','memory'].includes(source)?source:'unknown']++;
      if(headers['content-length']&&Number.isFinite(size))entry.knownBytes+=size;else entry.unknownByteResponses++;
    }
    assetRequests.set(key,previous);sessionAssetRequests.set(sessionKey,sessionPrevious);
  });
  await page.locator('#name').fill('Browser compatibility observer');
  if(!firefox&&process.env.OVERTE_LAB_PROFILE==='1'){profiler=await page.context().newCDPSession(page);await profiler.send('Profiler.enable');await profiler.send('Profiler.setSamplingInterval',{interval:1000});report.cpuProfileStartedAt=new Date().toISOString();await profiler.send('Profiler.start');}
  if(report.uploadProfileRequested)await page.evaluate(()=>window.__hubUploadProfile?.setPhase('loading'));
  await page.locator('#join').click();
  await page.waitForFunction(()=>window.__overte?.connected||document.querySelector('#notice[data-kind="error"]'),null,{timeout:60000});
  const state=await page.evaluate(()=>({connected:window.__overte?.connected,notice:document.querySelector('#notice')?.textContent}));
  if(!state.connected)throw Error(state.notice||'Public-world connection refused');
  report.connectedAt=new Date().toISOString();report.runtimeHelperSHA256=await ownedRuntimeHelpers();
  report.webGL=await page.evaluate(()=>{const gl=document.querySelector('#world canvas').getContext('webgl2');const ext=gl?.getExtension('WEBGL_debug_renderer_info');return gl?{vendor:gl.getParameter(ext?.UNMASKED_VENDOR_WEBGL||gl.VENDOR),renderer:gl.getParameter(ext?.UNMASKED_RENDERER_WEBGL||gl.RENDERER),parallelShaderCompile:!!gl.getExtension('KHR_parallel_shader_compile')}:null;});
  await page.waitForFunction(()=>window.__overte.entityCount>20,null,{timeout:30000});
  report.performance=[];
  const loadingDeadline=Date.now()+Number(process.env.OVERTE_LAB_LOADING_TIMEOUT||90)*1000;
  while(Date.now()<loadingDeadline){await page.waitForTimeout(3000);const sample=await page.evaluate(()=>({at:Date.now(),...window.__overte.performance,entityCount:window.__overte.entityCount,position:window.__overte.pose?.position}));report.performance.push(sample);await writeFile(path.join(output,'public-hub-progress.json'),JSON.stringify({startedAt:report.startedAt,sample})+'\n');if(!sample.position)throw Error(await page.locator('#notice').textContent());if(!report.earlyMovement&&sample.loadedModels>=10&&sample.meshColliders>0){const before=await page.evaluate(()=>window.__overte.pose);await page.locator('#world canvas').evaluate(element=>element.focus());await page.keyboard.down('KeyW');await page.waitForTimeout(250);await page.keyboard.up('KeyW');await page.waitForTimeout(300);report.earlyMovement=await page.evaluate(before=>({before,after:window.__overte.pose,nativePose:window.__hubNativePose}),before);await screenshot('public-hub-loading.png');}if(sample.queuedModels===0&&sample.loadingModels===0&&sample.compilingGraphics===0)break;}
  requireWorldLoadingReady(report.performance.at(-1));
  if(report.uploadProfileRequested)await page.evaluate(()=>window.__hubUploadProfile?.setPhase('steady'));
  for(let i=0;i<4;i++){
    await page.waitForTimeout(3000);
    report.performance.push(await page.evaluate(()=>({at:Date.now(),...window.__overte.performance,entityCount:window.__overte.entityCount,position:window.__overte.pose?.position})));
  }
  report.steadyFluidPerformance=assessFluidPerformance(report.performance.slice(-2));
  const active=await page.evaluate(()=>window.__overte.connected);if(!active)throw Error(await page.locator('#notice').textContent());
  report.before=await page.evaluate(()=>({pose:window.__overte.pose,entityCount:window.__overte.entityCount,avatarCount:window.__overte.avatarCount,audio:window.__overte.audio}));
  await page.locator('#world canvas').evaluate(element=>element.focus());await page.keyboard.down('KeyW');await page.waitForTimeout(1500);await page.keyboard.up('KeyW');await page.waitForTimeout(500);
  report.after=await page.evaluate(()=>({pose:window.__overte.pose,performance:window.__overte.performance,nativePose:window.__hubNativePose,traffic:window.__hubTraffic,entityHosts:[...window.__hubEntitySummary.values()].reduce((result,entity)=>{result[entity.hostType]=(result[entity.hostType]||0)+1;return result;},{}),localOnlyEntities:[...window.__hubEntitySummary.values()].filter(e=>e.clientOnly).length}));
  report.walkFluidPerformance=assessFluidPerformance([report.performance.at(-1),report.after.performance]);
  report.movementMeters=Math.hypot(report.after.pose.position.x-report.before.pose.position.x,report.after.pose.position.z-report.before.pose.position.z);
  assert(report.movementMeters>0.5,'Actual public-world keyboard movement must exceed0.5m');
  assert(report.after.nativePose&&Date.now()-report.after.nativePose.at<2500,'Native own-avatar observation must be current');
  report.nativePoseDifferenceMeters=Math.hypot(...['x','y','z'].map(axis=>report.after.pose.position[axis]-report.after.nativePose.position[axis]));
  assert(report.nativePoseDifferenceMeters<0.5,'Actual native avatar must follow browser position within0.5m');
  report.events=await page.locator('#events').textContent();
  report.webGL=await page.evaluate(()=>{const gl=document.querySelector('#world canvas').getContext('webgl2');const ext=gl?.getExtension('WEBGL_debug_renderer_info');return gl?{vendor:gl.getParameter(ext?.UNMASKED_VENDOR_WEBGL||gl.VENDOR),renderer:gl.getParameter(ext?.UNMASKED_RENDERER_WEBGL||gl.RENDERER)}:null;});
  await screenshot('public-hub.png');
  report.pageErrors=errors;
  // One-shot diagnostic only after initial steady/walking samples and screenshot.
  // Leave immediately afterward; rejoin creates a fresh World/performance ring.
  if(process.env.OVERTE_LAB_DRAW_CENSUS==='1')report.drawCensus=await page.evaluate(()=>{
    if(!window.__overte?.connected||typeof window.__overte.drawCensus!=='function')throw Error('Draw census is unavailable in this connected browser bundle');
    const startedAt=Date.now(),data=window.__overte.drawCensus();return{admissionOrdinal:1,startedAt,finishedAt:Date.now(),data};
  });
  // Each generation's performance samples are already copied above. No later
  // metric from this diagnostic is added to its acceptance samples; rejoin gets
  // a fresh World/ring. This optional request performs no world interaction.
  if(report.asyncDrawCensusRequested)report.asyncDrawCensus=[await page.evaluate(collectHubAsyncDrawCensus,1)];
  if(report.uploadProfileRequested)await page.evaluate(()=>window.__hubUploadProfile?.setPhase('leaving'));
  await page.locator('#leave').click();
  if(process.env.OVERTE_LAB_RECONNECT==='1'){
    await page.waitForTimeout(3500);if(report.uploadProfileRequested)await page.evaluate(()=>window.__hubUploadProfile?.setPhase('reloading'));await page.locator('#join').click();
    await page.waitForFunction(()=>window.__overte?.connected||document.querySelector('#notice[data-kind="error"]'),null,{timeout:60000});
    if(!await page.evaluate(()=>window.__overte.connected))throw Error(await page.locator('#notice').textContent());
    await page.waitForFunction(()=>window.__overte.entityCount>20&&window.__overte.performance.meshColliders>0&&window.__overte.performance.loadingModels===0&&window.__overte.performance.queuedModels===0&&window.__overte.performance.compilingGraphics===0,null,{timeout:90000});
    if(report.uploadProfileRequested)await page.evaluate(()=>window.__hubUploadProfile?.setPhase('rejoined-ready'));
    report.reconnectedSteadySamples=[];for(let index=0;index<4;index++){await page.waitForTimeout(3000);report.reconnectedSteadySamples.push(await page.evaluate(()=>window.__overte.performance));}
    report.reconnectedSteadyFluidPerformance=assessFluidPerformance(report.reconnectedSteadySamples.slice(-2));
    report.reconnectedRuntimeHelperSHA256=await ownedRuntimeHelpers();report.reconnected=await page.evaluate(()=>({at:Date.now(),pose:window.__overte.pose,performance:window.__overte.performance,entityCount:window.__overte.entityCount,nativePose:window.__hubNativePose}));
    await page.locator('#world canvas').evaluate(element=>element.focus());await page.keyboard.down('KeyW');await page.waitForTimeout(1000);await page.keyboard.up('KeyW');await page.waitForTimeout(300);
    report.reconnectedAfterMovement=await page.evaluate(()=>({pose:window.__overte.pose,nativePose:window.__hubNativePose,performance:window.__overte.performance}));
    report.reconnectedWalkFluidPerformance=assessFluidPerformance([report.reconnected.performance,report.reconnectedAfterMovement.performance]);
    const before=report.reconnected.pose.position,after=report.reconnectedAfterMovement.pose.position;report.reconnectedMovementMeters=Math.hypot(after.x-before.x,after.z-before.z);assert(report.reconnectedMovementMeters>0.5,'Fully reloaded public-world session must move after rejoin');assert(Math.abs(after.y-before.y)<3,'Rejoined avatar stays on the actual nearby world');const native=report.reconnectedAfterMovement.nativePose;assert(native&&Date.now()-native.at<2500,'Rejoined native avatar observation must be current');report.reconnectedNativeDifferenceMeters=Math.hypot(...['x','y','z'].map(axis=>after[axis]-native.position[axis]));assert(report.reconnectedNativeDifferenceMeters<0.5,'Rejoined actual native avatar must follow browser movement');
    // Snapshot collection follows all rejoined movement/native/frame checks.
    if(report.asyncDrawCensusRequested)report.asyncDrawCensus.push(await page.evaluate(collectHubAsyncDrawCensus,2));
    await page.locator('#leave').click();
  }
  report.fluidMovementAcceptancePassed=[report.steadyFluidPerformance,report.walkFluidPerformance,...(report.reconnected ? [report.reconnectedSteadyFluidPerformance,report.reconnectedWalkFluidPerformance] : [])].every(value=>value?.passed);
  if(process.env.OVERTE_LAB_REQUIRE_FLUID==='1')assert(report.fluidMovementAcceptancePassed,'Actual loaded-world, walking and reconnect measurements must meet30FPS, p95<=66.7ms and no steady stall>250ms');
  report.completed=true;
} catch(error){report.error=error.message;process.exitCode=1;}
finally{
  if(profiler){try{const {profile}=await profiler.send('Profiler.stop');const stoppedAt=new Date().toISOString(),bytes=JSON.stringify(profile),filename='public-hub-cpu-profile-'+report.startedAt.replace(/[:.]/g,'-')+'.json';await writeFile(path.join(output,filename),bytes,{flag:'wx'});await writeFile(path.join(output,'public-hub-cpu-profile.json'),bytes);report.cpuProfile={filename,sha256:createHash('sha256').update(bytes).digest('hex'),startedAt:report.cpuProfileStartedAt,stoppedAt,sampleCount:profile.samples?.length||0,durationMs:(profile.endTime-profile.startTime)/1000,startWorldSHA256:report.startSourceSHA256['browser-client/src/world.ts'],startMainSHA256:report.startSourceSHA256['browser-client/src/main.ts'],startDistributionManifestSHA256:createHash('sha256').update(JSON.stringify(report.startDistributionManifest)).digest('hex')};await profiler.detach();}catch(error){report.profileError=error.message;}}
  if(page){try{report.glCalls=await page.evaluate(()=>window.__hubGLCalls);report.uploadProfile=report.uploadProfileRequested?await page.evaluate(()=>window.__hubUploadProfile?.snapshot()||{enabled:false}):{enabled:false};report.longTasks=await page.evaluate(()=>window.__hubLongTasks);report.resources=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>({url:r.name,start:r.startTime,duration:r.duration,transferSize:r.transferSize,decodedBodySize:r.decodedBodySize})));report.finalDiagnostics=await page.evaluate(()=>({state:window.__overte,entityHosts:[...window.__hubEntitySummary.values()].reduce((result,entity)=>{result[entity.hostType]=(result[entity.hostType]||0)+1;return result;},{}),localOnlyEntities:[...window.__hubEntitySummary.values()].filter(e=>e.clientOnly).length,nativePose:window.__hubNativePose,traffic:window.__hubTraffic,messages:window.__hubMessages, notice:document.querySelector('#notice')?.textContent,events:document.querySelector('#events')?.textContent}));}catch{}}
  await browser?.close();report.finishedAt=new Date().toISOString();
  for(const file of sourceFiles){
    try{report.sourceSHA256??={};report.sourceSHA256[file]=createHash('sha256').update(await readFile(path.join(repo,file))).digest('hex');}catch{}
  }
  report.distributionManifest=await distributionManifest();
  report.assetTransfers={categories:assetCategoryTotals([...assetRequests.values()]),uniqueURLs:assetRequests.size,requests:[...assetRequests.values()].reduce((sum,value)=>sum+value.requests,0),knownBytes:[...assetRequests.values()].reduce((sum,value)=>sum+value.knownBytes,0),unknownByteResponses:[...assetRequests.values()].reduce((sum,value)=>sum+value.unknownByteResponses,0),duplicateRequests:[...assetRequests.values()].reduce((sum,value)=>sum+Math.max(0,value.requests-1),0),sources:Object.fromEntries(['download','shared','memory','unknown'].map(source=>[source,[...assetRequests.values()].reduce((sum,value)=>sum+value.sources[source],0)])),entries:[...assetRequests].map(([urlSHA256,value])=>({urlSHA256,...value}))};
  report.assetTransfers.sessions=assetSessionTotals([...sessionAssetRequests.values()]);
  await writeFile(path.join(output,'public-hub.json'),JSON.stringify(report,null,2)+'\n');
  await writeFile(path.join(output,'public-hub-'+report.startedAt.replace(/[:.]/g,'-')+'.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({startedAt:report.startedAt,finishedAt:report.finishedAt,completed:report.completed,error:report.error,browserVersion:report.browserVersion,webGL:report.webGL,performanceSamples:report.performance?.length,lastPerformance:report.performance?.at(-1),asyncDrawCensus:report.asyncDrawCensus,assetTransfers:{...report.assetTransfers,entries:undefined,sessions:report.assetTransfers.sessions.map(({entries,...session})=>session)},report:path.relative(repo,path.join(output,'public-hub.json'))}));
}
