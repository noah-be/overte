// SPDX-License-Identifier: Apache-2.0
// Actual packaged/native FBX bytes, production-built workers and codec factories.
// This proof uses no domain connection or world writes and needs no GPU context.
import {chromium,firefox} from '@playwright/test';
import {build} from 'vite';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {createNativeBakedFbxFixture} from '../fixtures/native-baked-fbx.mjs';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const fixtures=process.env.OVERTE_FBX_POOL_FIXTURES?JSON.parse(process.env.OVERTE_FBX_POOL_FIXTURES):[path.join(client,'public/default-avatar/mannequin/mannequin.fbx')];
assert(Array.isArray(fixtures)&&fixtures.length>0&&fixtures.length<=8,'Provide 1–8 actual cached FBX files');
const output=process.env.OVERTE_FBX_POOL_EVIDENCE||path.join(client,'build/model-fbx-pool-proof.json');
const directory=await mkdtemp(path.join(tmpdir(),'overte-fbx-pool-proof-'));
const report={startedAt:new Date().toISOString(),completed:false,browserKind:process.env.OVERTE_FBX_POOL_BROWSER||'chromium',fixtures:[]};
let server,browser;
try{
  const bytes=await Promise.all(fixtures.map(async file=>{const bytes=await readFile(file);assert(bytes.length<=32*1024*1024);return bytes;}));
  const kinds=fixtures.map(()=>process.env.OVERTE_FBX_POOL_FIXTURES?'cached-native-FBX':'packaged-native-mannequin');
  for(const custom of [false,true]){bytes.push(Buffer.from(createNativeBakedFbxFixture(custom).buffer));kinds.push(custom?'authored-native-custom-Draco':'authored-ordinary-Draco');}
  await build({configFile:false,root:client,logLevel:'warn',worker:{format:'es'},build:{lib:{entry:path.join(client,'tests/integration/model-fbx-pool-entry.ts'),formats:['es'],fileName:'proof'},outDir:directory,emptyOutDir:true,target:'es2022'}});
  const mime={'.js':'application/javascript','.wasm':'application/wasm','.fbx':'application/octet-stream'};
  server=createServer(async(req,res)=>{try{
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Owned FBX preparation proof</title>');return;}
    const fixture=/^\/fixture\/(\d+)$/.exec(pathname);if(fixture){const data=bytes[Number(fixture[1])];if(!data){res.writeHead(404);res.end();return;}res.setHeader('Content-Type','application/octet-stream');res.end(data);return;}
    if(pathname.startsWith('/unused-textures/')){res.writeHead(404);res.end();return;}
    const file=path.resolve(directory,'.'+decodeURIComponent(pathname));if(!file.startsWith(directory+path.sep)){res.writeHead(403);res.end();return;}
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.end(await readFile(file));
  }catch{res.writeHead(404);res.end();}});
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const origin=`http://127.0.0.1:${server.address().port}`;
  const browserType=report.browserKind==='firefox'?firefox:chromium;
  browser=await browserType.launch({headless:true});report.browserVersion=browser.version();
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin);
  report.actual=await page.evaluate(async count=>{
    const api=await import('/proof.js');
    const NativeWorker=window.Worker;let workersCreated=0,workersTerminated=0;
    window.Worker=class extends NativeWorker{constructor(...args){super(...args);workersCreated++;}terminate(){workersTerminated++;return super.terminate();}};
    const pool=new api.BakedFbxPreparePool({limit:2});
    const inputs=await Promise.all(Array.from({length:count},(_,i)=>fetch('/fixture/'+i).then(response=>response.arrayBuffer())));
    const baselineInputs=inputs.map(input=>input.slice(0));
    let ticks=0,maxGap=0,last=performance.now();const ticker=setInterval(()=>{const now=performance.now();maxGap=Math.max(maxGap,now-last);last=now;ticks++;},16);
    const started=performance.now();const requests=inputs.map(input=>pool.prepare(input));
    const initial={...pool.counters};const activeDetached=inputs.slice(0,Math.min(2,count)).every(input=>input.byteLength===0);
    let prepared;try{prepared=await Promise.all(requests);}finally{clearInterval(ticker);}
    const elapsed=performance.now()-started,ownWorkers=workersCreated,counters={...pool.counters};pool.dispose();
    const poolCleanup=workersTerminated===ownWorkers;
    const records=[];for(let i=0;i<count;i++){
      const actual=await api.inspect(prepared[i].buffer),expected=await api.inspect(await api.baseline(baselineInputs[i]));
      records.push({index:i,actual,expected,phases:prepared[i].phases});
    }
    // A genuine worker that cannot process cooperative messages proves hard
    // deadline termination, rather than simulating a completed parser response.
    const blob=URL.createObjectURL(new Blob(['onmessage=()=>{const end=performance.now()+2000;while(performance.now()<end){};postMessage({late:true})}'],{type:'text/javascript'}));
    const stalled=new api.BakedFbxPreparePool({limit:1,deadlineMs:75,workerFactory:()=>new Worker(blob)});
    const deadlineStart=performance.now();let deadlineError='';try{await stalled.prepare(new ArrayBuffer(8));}catch(error){deadlineError=error.message;}
    const deadlineElapsed=performance.now()-deadlineStart,deadlineCounters={...stalled.counters};stalled.dispose();URL.revokeObjectURL(blob);
    window.Worker=NativeWorker;
    return{records,initial,counters,ownWorkers,poolCleanup,activeDetached,elapsed,ticks,maxGap,deadlineError,deadlineElapsed,deadlineCounters};
  },bytes.length);
  for(let i=0;i<report.actual.records.length;i++){
    const record=report.actual.records[i];assert.deepEqual(record.actual,record.expected,'Worker preparation must preserve exact baseline FBX bytes, geometry/material groups and native skin bones');assert(record.actual.meshes>0);
    report.fixtures.push({index:i,fixtureKind:kinds[i],inputBytes:bytes[i].length,inputSHA256:createHash('sha256').update(bytes[i]).digest('hex'),...record});
  }
  assert.equal(report.actual.ownWorkers,Math.min(2,bytes.length),'No nested decoder workers are created by full preparation');
  assert(report.actual.activeDetached);assert(report.actual.poolCleanup);assert.equal(report.actual.counters.outstanding,0);assert.equal(report.actual.counters.inputBytes,0);
  assert.match(report.actual.deadlineError,/bounded deadline/);assert(report.actual.deadlineElapsed>=60&&report.actual.deadlineElapsed<2000);assert.equal(report.actual.deadlineCounters.workers,0);
  assert.deepEqual(errors,[]);report.pageErrors=0;report.completed=true;
}catch(error){report.error=error.stack;process.exitCode=1;}
finally{await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));await rm(directory,{recursive:true,force:true});report.finishedAt=new Date().toISOString();await mkdir(path.dirname(output),{recursive:true});await writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({completed:report.completed,browserVersion:report.browserVersion,fixtures:report.fixtures.length,error:report.error}));}
