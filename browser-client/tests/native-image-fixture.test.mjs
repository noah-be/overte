// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Executes the production native author script. These tests do not claim native GPU proof.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('./integration/native-image-fixture.js',import.meta.url),'utf8');
function fixture(canRez=true,renderMethod=0,aaState={mode:1,stop:false,freeze:false},emissive=true){
 let time=0,tick,draw,ending,command={},quit=0;const entities=new Map([['baseline',{name:'Browser Lab untouched'}]]),deleted=[],prefetches=[],snapshots=[],records=[],jobNames=[],resource={state:1};
 const aa=Object.freeze({...aaState});
 const signal=callback=>({connect(fn){callback(fn);}}),config={prefix:'Native Image Fixture unit ',center:{x:60,y:10,z:0},camera:{x:60,y:10,z:4},outputDirectory:'/owned',commandURL:'http://fixture/command.json',emissive,assets:{opaque:{original:'http://fixture/opaque.png',compressed:'http://fixture/opaque.texmeta.json'},mask:{original:'http://fixture/mask.png',compressed:'http://fixture/mask.texmeta.json'}}};
 const context=vm.createContext({NATIVE_IMAGE_FIXTURE:config,print(line){records.push(JSON.parse(line.split('NATIVE_IMAGE_FIXTURE ')[1]));},Date:{now(){return time;}},
  About:{buildVersion:'2026.04.1'},location:{isConnected:true},Audio:{muted:false},MyAvatar:{setGravity(g){this.gravity=g;}},Scene:{shouldRenderEntities:true},
  Camera:{mode:'',position:null,orientation:{x:0,y:0,z:0,w:1},frustum:{fieldOfView:45,aspectRatio:4/3},lookAt(){}},
  Entities:{serversExist(){return true;},canRez(){return canRez;},addEntity(properties){const id='owned-'+entities.size;entities.set(id,{...properties});return id;},getEntityProperties(id){return entities.get(id)||{};},editEntity(id,properties){Object.assign(entities.get(id),properties);},deleteEntity(id){deleted.push(id);entities.delete(id);}},
  TextureCache:{prefetch(url,type){prefetches.push({url,type});return resource;}},Render:{renderMethod,getConfig(name){if(name==='RenderMainView.AntialiasingSetup')return aa;jobNames.push(name);assert.equal(name,context.Render.renderMethod===0?'RenderMainView.DrawTransparentDeferred':'RenderMainView.DrawTransparents');return{enabled:true,newStats:{connect(fn){draw=fn;},disconnect(fn){if(draw===fn)draw=null;}}};}},
  Snapshot:{setSnapshotsLocation(p){assert.equal(p,'/owned');},setSnapshotFormat(p){assert.equal(p,'PNG');}},Window:{stillSnapshotTaken:signal(()=>{}),takeSnapshot(...args){snapshots.push(args);}},Menu:{triggerOption(name){assert.equal(name,'Quit');quit++;}},
  Script:{scriptEnding:signal(fn=>ending=fn),setInterval(fn){tick=fn;},setTimeout(){}},
  XMLHttpRequest:class{open(method,url){assert.equal(method,'GET');assert(url.startsWith(config.commandURL));}send(){this.readyState=4;this.status=200;this.responseText=JSON.stringify(command);this.onreadystatechange();}}
 });
 vm.runInContext(source,context);return{context,entities,deleted,prefetches,snapshots,records,resource,jobNames,get drawCallback(){return draw;},setRenderMethod(value){context.Render.renderMethod=value;},run(){tick();},command(c){command=c;tick();},draw(n=1){while(n--)draw();},advance(ms){time+=ms;},end(){ending();},get quit(){return quit;}};
}
test('native author creates exactly four owned expiring entities and uses the actual default texture role',()=>{
 const f=fixture();f.run();assert.equal(f.entities.size,5);for(const[id,e]of f.entities)if(id!=='baseline'){assert(e.name.startsWith('Native Image Fixture unit '));assert.equal(e.lifetime,360);assert.equal(e.collisionless,true);}assert.deepEqual(f.prefetches,[{url:'http://fixture/opaque.png',type:0}]);assert.equal(f.context.Audio.muted,true);assert.equal(f.context.MyAvatar.gravity,0);
 f.command({sequence:1,action:'case',name:'mask',mode:'compressed'});assert.deepEqual(f.prefetches.at(-1),{url:'http://fixture/mask.texmeta.json',type:0});const images=[...f.entities.values()].filter(e=>e.type==='Image');assert.equal(images.length,2);assert.equal(images.filter(e=>e.visible).length,1);assert.equal(images.find(e=>e.visible).imageURL,'http://fixture/mask.texmeta.json');
});
test('a snapshot requires actual FINISHED texture state and three minimum readiness frames and a full pinned16-frame TAA capture cycle',()=>{
 const f=fixture();f.run();f.command({sequence:1,action:'snapshot'});f.draw(10);f.run();assert.equal(f.snapshots.length,0);f.resource.state=3;f.run();assert.equal(f.snapshots.length,0,'Frames before FINISHED must never satisfy readiness');f.draw(2);f.run();assert.equal(f.snapshots.length,0);f.draw();f.run();assert.equal(f.snapshots.length,0);f.draw(13);f.run();assert.equal(f.snapshots.length,1);f.command({sequence:2,action:'snapshot'});f.run();f.draw(15);f.run();assert.equal(f.snapshots.length,1);f.draw();f.run();assert.equal(f.snapshots.length,2);
});
test('snapshot readiness retains the 29-second native deadline instead of capturing missing texture pixels',()=>{
 const f=fixture();f.run();f.command({sequence:1,action:'snapshot'});f.draw(100);f.advance(29000);f.run();assert.equal(f.snapshots.length,0);assert.equal(f.records.filter(r=>r.kind==='snapshot-error').length,1);assert.equal(f.records.find(r=>r.kind==='snapshot-error').data.sequence,1);
});
test('creation refusal performs no entity writes or texture prefetch and never elevates permissions',()=>{
 const f=fixture(false);f.run();assert.equal(f.entities.size,1);assert.deepEqual(f.prefetches,[]);assert.deepEqual(f.deleted,[]);assert.equal(f.records.find(r=>r.kind==='refused').kind,'refused');assert.equal(f.quit,1);
});
test('cleanup only removes IDs owned by this author and still carrying its exact prefix',()=>{
 const f=fixture();f.run();const id=[...f.entities.keys()].find(id=>id!=='baseline');f.entities.get(id).name='Unrelated replacement';f.command({sequence:1,action:'cleanup'});f.end();assert.equal(f.deleted.length,3);assert(f.entities.has('baseline'));assert(f.entities.has(id));assert(f.deleted.every(id=>id.startsWith('owned-')));assert.equal(f.records.filter(r=>r.kind==='cleanup-sent').length,1);
});

test('normal forward rendering observes the real DrawTransparents job without changing render defaults',()=>{
 const f=fixture(true,1);f.run();assert.deepEqual(f.jobNames,['RenderMainView.DrawTransparents']);assert.equal(f.context.Render.renderMethod,1);f.command({sequence:1,action:'snapshot'});f.resource.state=3;f.run();f.draw(3);f.run();assert.equal(f.snapshots.length,1);const diagnostic=f.records.find(r=>r.kind==='snapshot-ready').data.diagnostic;assert.equal(diagnostic.renderMethod,1);assert.equal(diagnostic.renderStatsJob,'RenderMainView.DrawTransparents');
});
test('changing the real render branch invalidates former job signals and requires three new frames',()=>{
 const f=fixture();f.run();f.resource.state=3;f.draw(3);f.run();f.command({sequence:1,action:'snapshot'});const former=f.drawCallback;f.setRenderMethod(1);f.run();for(let i=0;i<10;i++)former();f.run();assert.equal(f.snapshots.length,0);f.draw(2);f.run();assert.equal(f.snapshots.length,0);f.draw();f.run();assert.equal(f.snapshots.length,1);assert.deepEqual(f.jobNames,['RenderMainView.DrawTransparentDeferred','RenderMainView.DrawTransparents']);
});

test('an unknown render branch disconnects stale stats and cannot reuse ready frames after restoration',()=>{
 const f=fixture();f.run();f.resource.state=3;f.run();f.draw(3);f.run();f.command({sequence:1,action:'snapshot'});const former=f.drawCallback;
 f.setRenderMethod(99);f.run();former();f.run();assert.equal(f.snapshots.length,0);assert.equal(f.drawCallback,null);
 f.setRenderMethod(0);f.run();for(let i=0;i<10;i++)former();f.run();assert.equal(f.snapshots.length,0);f.draw(15);f.run();assert.equal(f.snapshots.length,0);f.draw();f.run();assert.equal(f.snapshots.length,1);
});

test('the native TAA capture readback never mutates the installed AA configuration',()=>{
 const f=fixture();f.run();f.resource.state=3;f.run();f.command({sequence:1,action:'snapshot'});f.draw(16);f.run();
 const aa=f.records.find(record=>record.kind==='snapshot-ready').data.diagnostic.antialiasing;
 assert.deepEqual(aa,{kind:'taa',mode:1,stopped:false,frozen:false,minimumSnapshotFrames:16});
 assert.equal(f.context.Render.renderMethod,0);assert.equal(f.snapshots.length,1);
});

test('missing native AA readback cannot turn finite ticks into an invented capture policy',()=>{
 const f=fixture(true,0,{});f.run();f.resource.state=3;f.run();f.command({sequence:1,action:'snapshot'});f.draw(1000);f.run();assert.equal(f.snapshots.length,0);
 f.advance(29000);f.run();assert.equal(f.records.filter(record=>record.kind==='snapshot-error').length,1);
 assert.equal(f.records.find(record=>record.kind==='snapshot-error').data.diagnostic.antialiasing.kind,'unavailable');
});

test('opt-in lit author preserves four owned IDs and actual emissive:false through both image asset modes',()=>{
 const f=fixture(true,0,{mode:1,stop:false,freeze:false},false);f.run();const owned=[...f.entities.keys()].filter(id=>id!=='baseline');assert.equal(owned.length,4);
 for(const mode of ['original','compressed']){f.command({sequence:mode==='original'?1:2,action:'case',name:'opaque',mode});const visible=[...f.entities.values()].filter(e=>e.type==='Image'&&e.visible);assert.equal(visible.length,1);assert.equal(visible[0].emissive,false);assert.equal(visible[0].imageURL,'http://fixture/opaque'+(mode==='original'?'.png':'.texmeta.json'));assert.deepEqual([...f.entities.keys()].filter(id=>id!=='baseline'),owned);}
 assert.equal(f.context.Render.renderMethod,0);f.end();assert.deepEqual(f.deleted,owned);assert(f.entities.has('baseline'));
});
test('malformed lighting mode refuses before any native entity mutation or texture allocation',()=>{assert.throws(()=>fixture(true,0,{mode:1,stop:false,freeze:false},'false'),/Unknown fixed Image lighting cohort/);});
