// SPDX-License-Identifier: Apache-2.0
// Real public Hub asset, real browser WASM decoder, unchanged Three FBX parser.
// This focused asset test is independent of domain/world acceptance.
import {chromium} from '@playwright/test';
import {spawn} from 'node:child_process';
import {mkdir,writeFile,readdir,readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const output=path.join(repo,'build/browser-hub-lab/decoder');
const port=Number(process.env.OVERTE_DECODER_PROBE_PORT||5179);
const origin=`http://127.0.0.1:${port}`;
const asset=process.env.OVERTE_DECODER_PROBE_ASSET||'https://content.overte.org/Bazaar/Worlds/HQ_HiFi/content/bridge-wood-2/baked/bridge-wood-2.baked.fbx';
const production=process.env.OVERTE_DECODER_PROBE_PRODUCTION==='1';
const report={startedAt:new Date().toISOString(),completed:false,asset,productionBuild:production};
let vite,browser;
try{
 await mkdir(output,{recursive:true});
 try{await fetch(origin,{signal:AbortSignal.timeout(300)});throw Error('Refusing to reuse an unowned test port');}catch(error){if(error.message==='Refusing to reuse an unowned test port')throw error;}
 vite=spawn(process.execPath,['node_modules/vite/bin/vite.js',...(production?['preview']:[]),'--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:path.join(repo,'browser-client'),stdio:'ignore'});
 for(let i=0;i<50;i++){try{if((await fetch(origin)).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 const response=await fetch(asset,{signal:AbortSignal.timeout(15000)});assert.equal(response.status,200);const bytes=Buffer.from(await response.arrayBuffer());report.assetSHA256=createHash('sha256').update(bytes).digest('hex');report.inputBytes=bytes.length;
 browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--disable-dev-shm-usage']});report.browserVersion=browser.version();
 const page=await browser.newPage();
 if(production&&process.env.OVERTE_DECODER_PROBE_COMPARE==='1'){for(const file of ['three.module.js','three.core.js'])await page.route(`${origin}/node_modules/three/build/${file}`,async route=>route.fulfill({status:200,contentType:'application/javascript',body:await readFile(path.join(repo,'browser-client/node_modules/three/build',file))}));}
 await page.route(`${origin}/actual-bridge.fbx`,route=>route.fulfill({status:200,contentType:'application/octet-stream',body:bytes}));
 await page.goto(origin);
 const files=production?await readdir(path.join(repo,'browser-client/dist/assets')):[];
 const imports=production?{baked:'/assets/'+files.find(f=>/^baked-fbx-.*\.js$/.test(f)),fbx:'/assets/'+files.find(f=>/^FBXLoader-.*\.js$/.test(f))}:{baked:'/src/baked-fbx.ts',fbx:'/node_modules/three/examples/jsm/loaders/FBXLoader.js'};
 imports.compare=process.env.OVERTE_DECODER_PROBE_COMPARE==='1';imports.three='/node_modules/three/build/three.module.js';
 report.geometry=await page.evaluate(async imports=>{
  const {adaptBakedFbx}=await import(imports.baked);const {FBXLoader}=await import(imports.fbx);
  const raw=await(await fetch('/actual-bridge.fbx')).arrayBuffer();const start=performance.now();let restored;try{restored=await adaptBakedFbx(raw);}catch(error){throw Error('Native baked decode failed: '+JSON.stringify(error)+' '+String(error?.message||error));}
  const path=new URL('.', location.origin+'/').href;
  const group=new FBXLoader().parse(restored,path);let meshes=0,vertices=0,uvs=0,groups=0;const materialIndices=new Set();
  group.traverse(o=>{if(o.isMesh){meshes++;vertices+=o.geometry.getAttribute('position')?.count||0;uvs+=o.geometry.getAttribute('uv')?.count||0;groups+=o.geometry.groups.length;for(const group of o.geometry.groups)materialIndices.add(group.materialIndex);}});
  const result={meshes,vertices,uvs,groups,materialIndices:[...materialIndices],restoredBytes:restored.byteLength,decodeAndParseMilliseconds:performance.now()-start};
  result.materialAudit=[];group.traverse(mesh=>{if(!mesh.isMesh)return;const materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];result.materialAudit.push({groups:mesh.geometry.groups.length,triangles:(mesh.geometry.index?.count??mesh.geometry.attributes.position.count)/3,materials:materials.length,transparentMaterials:materials.filter(m=>m.transparent||m.opacity<1).length,transparentGroups:mesh.geometry.groups.filter(g=>materials[g.materialIndex]?.transparent||materials[g.materialIndex]?.opacity<1).length,opacityValues:[...new Set(materials.map(m=>m.opacity))],attributes:Object.keys(mesh.geometry.attributes)});});
  if(imports.compare){
    const baseline=new FBXLoader().parse(await adaptBakedFbx(raw,undefined,{preserveTriangleOrder:true}),path);
    const THREE=await import(imports.three);
    async function membership(root){const faces=[];const materialStates=[];let groupCount=0;root.updateMatrixWorld(true);root.traverse(mesh=>{if(!mesh.isMesh)return;materialStates.push(...(Array.isArray(mesh.material)?mesh.material:[mesh.material]).map(m=>({opacity:m.opacity,transparent:m.transparent})));const p=mesh.geometry.getAttribute('position'),uv=mesh.geometry.getAttribute('uv'),n=mesh.geometry.getAttribute('normal'),idx=mesh.geometry.index;groupCount+=mesh.geometry.groups.length;for(const group of mesh.geometry.groups)for(let at=group.start;at<group.start+group.count;at+=3){const corners=[0,1,2].map(offset=>{const i=idx?idx.getX(at+offset):at+offset;return{p:[p.getX(i),p.getY(i),p.getZ(i)],uv:uv?[uv.getX(i),uv.getY(i)]:null,n:n?[n.getX(i),n.getY(i),n.getZ(i)]:null};});faces.push(JSON.stringify({material:group.materialIndex,corners,matrix:mesh.matrixWorld.elements}));}});faces.sort();const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(faces)));return{triangles:faces.length,groups:groupCount,materialStates,sha256:[...new Uint8Array(bytes)].map(value=>value.toString(16).padStart(2,'0')).join('')};}
    const before=await membership(baseline),after=await membership(group);
    const canvas=document.createElement('canvas');canvas.width=256;canvas.height=256;const renderer=new THREE.WebGLRenderer({canvas,antialias:false,preserveDrawingBuffer:true});renderer.setSize(256,256,false);
    const textureCanvas=document.createElement('canvas');textureCanvas.width=2;textureCanvas.height=2;const ctx=textureCanvas.getContext('2d');['#ffffff','#777777','#333333','#bbbbbb'].forEach((color,i)=>{ctx.fillStyle=color;ctx.fillRect(i%2,Math.floor(i/2),1,1);});const texture=new THREE.CanvasTexture(textureCanvas);texture.magFilter=THREE.NearestFilter;texture.minFilter=THREE.NearestFilter;
    const camera=new THREE.PerspectiveCamera(40,1,.01,100);camera.position.set(2,1.5,3);camera.lookAt(0,0,0);
    function pixels(root){const scene=new THREE.Scene();scene.background=new THREE.Color(0x101020);root.traverse(mesh=>{if(mesh.isMesh){const previous=Array.isArray(mesh.material)?mesh.material:[mesh.material];mesh.material=previous.map((_,i)=>new THREE.MeshBasicMaterial({color:[0xff4444,0x44ff44,0x4444ff,0xffff44][i%4],map:texture,side:THREE.DoubleSide}));}});const bounds=new THREE.Box3().setFromObject(root),center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3()),scale=1.4/Math.max(size.x,size.y,size.z);root.position.sub(center).multiplyScalar(scale);root.scale.multiplyScalar(scale);scene.add(root);renderer.render(scene,camera);const gl=renderer.getContext(),bytes=new Uint8Array(256*256*4);gl.readPixels(0,0,256,256,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return{bytes,calls:renderer.info.render.calls};}
    const first=pixels(baseline),second=pixels(group);let different=0,visible=0;for(let i=0;i<first.bytes.length;i+=4){if(first.bytes[i]!==second.bytes[i]||first.bytes[i+1]!==second.bytes[i+1]||first.bytes[i+2]!==second.bytes[i+2])different++;if(first.bytes[i]!==16||first.bytes[i+1]!==16||first.bytes[i+2]!==32)visible++;}
    renderer.dispose();texture.dispose();result.materialGrouping={before,after,beforeDrawCalls:first.calls,afterDrawCalls:second.calls,pixelDifferences:different,visiblePixels:visible,diagnosticMaterialColors:true};
  }
  return result;
 },imports);
 assert(report.geometry.meshes>0);assert(report.geometry.vertices>0);assert.equal(report.geometry.uvs,report.geometry.vertices);
 if(!process.env.OVERTE_DECODER_PROBE_ASSET){assert.equal(report.geometry.meshes,1);assert.equal(report.geometry.vertices,11760);}
 if(process.env.OVERTE_DECODER_PROBE_MULTIMATERIAL==='1')assert(report.geometry.materialIndices.length>1,'Actual native custom material IDs decode into multiple FBX groups');
 if(report.geometry.materialGrouping){const m=report.geometry.materialGrouping;assert.equal(m.before.sha256,m.after.sha256,'Oriented triangle/UV/normal/material membership must be unchanged');assert.equal(m.pixelDifferences,0,'Actual opaque geometry pixels must remain equal');assert(m.visiblePixels>1000,'Actual decoded geometry is visible');assert(m.afterDrawCalls<=m.beforeDrawCalls,'Grouping cannot add draw calls');}
 report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally{await browser?.close();if(vite){vite.kill('SIGTERM');await new Promise(r=>{if(vite.exitCode!==null)r();else vite.once('exit',r);});}report.finishedAt=new Date().toISOString();await mkdir(output,{recursive:true});await writeFile(path.join(output,process.env.OVERTE_DECODER_PROBE_MULTIMATERIAL==='1'?(production?'baked-fbx-production-multimaterial.json':'baked-fbx-browser-multimaterial.json'):(production?'baked-fbx-production.json':'baked-fbx-browser.json')),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
