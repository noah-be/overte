// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted author for owned, expiring Image fixtures in an isolated domain only.
(function(){
 'use strict';
 var config=NATIVE_IMAGE_FIXTURE;
 if(config.emissive!==undefined&&typeof config.emissive!=='boolean')throw Error('Unknown fixed Image lighting cohort');
 var emissive=config.emissive!==false,owned=[],images=[],sequence=0,initialized=false,stopping=false,pending=null,frames=0,job=null,resource=null,current='',ready=false,lastDiagnostic=0,jobMethod=null,jobName='',statsCallback=null,statsGeneration=0,finishedFrames=null;
 function report(kind,data){print('NATIVE_IMAGE_FIXTURE '+JSON.stringify({kind:kind,at:Date.now(),data:data}));}
 function point(v){return v?{x:Number(v.x),y:Number(v.y),z:Number(v.z)}:null;}
 function rotation(v){return v?{x:Number(v.x),y:Number(v.y),z:Number(v.z),w:Number(v.w)}:null;}
 function anchor(){if(!location.isConnected||!Entities.serversExist())return;MyAvatar.position=config.camera;MyAvatar.velocity={x:0,y:0,z:0};Camera.mode='independent';Camera.position=config.camera;Camera.lookAt(config.center);Camera.orientation=rotation(Camera.orientation);}
 function add(p){p.name=config.prefix+p.name;p.lifetime=360;p.collisionless=true;var id=Entities.addEntity(p);if(!id||String(id).replace(/[{}-]/g,'')==='00000000000000000000000000000000')throw Error('Actual native fixture creation was refused');owned.push(id);return id;}
 function selectDrawStats(){
  var method=Number(Render.renderMethod);if(method!==0&&method!==1){if(job&&statsCallback&&job.newStats&&typeof job.newStats.disconnect==='function')try{job.newStats.disconnect(statsCallback);}catch(error){}statsGeneration++;job=null;jobMethod=null;jobName='';statsCallback=null;frames=0;finishedFrames=null;ready=false;if(pending)pending.frames=0;return;}
  if(method===jobMethod&&job)return;
  if(job&&statsCallback&&job.newStats&&typeof job.newStats.disconnect==='function')try{job.newStats.disconnect(statsCallback);}catch(error){}
  var generation=++statsGeneration;jobMethod=method;jobName=method===0?'RenderMainView.DrawTransparentDeferred':'RenderMainView.DrawTransparents';job=null;statsCallback=null;frames=0;finishedFrames=null;ready=false;if(pending)pending.frames=0;
  try{var candidate=Render.getConfig(jobName);if(candidate&&candidate.newStats&&typeof candidate.newStats.connect==='function'){job=candidate;statsCallback=function(){if(generation===statsGeneration&&Number(Render.renderMethod)===method)frames++;};job.newStats.connect(statsCallback);}}catch(error){job=null;}
 }
 function antialiasing(){
  if(Number(Render.renderMethod)===1)return {kind:'forward-msaa',minimumSnapshotFrames:3};
  try{var setup=Render.getConfig('RenderMainView.AntialiasingSetup');var mode=Number(setup.mode),stop=setup.stop,freeze=setup.freeze;
   if([0,1,2].indexOf(mode)<0||typeof stop!=='boolean'||typeof freeze!=='boolean')return {kind:'unavailable',minimumSnapshotFrames:null};
   // Pinned f91 AntialiasingSetup samples16 Halton offsets. Read only the
   // actual config: no AA, temporal-history or render-default mutation.
   return {kind:mode===1?'taa':mode===2?'fxaa':'none',mode:mode,stopped:stop,frozen:freeze,minimumSnapshotFrames:mode===1?16:3};
  }catch(error){return {kind:'unavailable',minimumSnapshotFrames:null};}
 }
 function diagnostic(){var f=Camera.frustum;return {connected:!!location.isConnected,serversExist:Entities.serversExist(),canRez:!!Entities.canRez(),current:current,emissive:emissive,renderedImages:images.map(function(id){var e=Entities.getEntityProperties(id,['visible','emissive','imageURL']);return {visible:e.visible===true,emissive:e.emissive,imageURLMatches:e.imageURL===config.assets[current.split('-')[0]][current.split('-')[1]]};}),renderMethod:Number(Render.renderMethod),renderStatsJob:jobName,resourceState:resource?Number(resource.state):null,antialiasing:antialiasing(),renderFrames:frames,finishedFrameBaseline:finishedFrames,renderJobAvailable:!!job,renderJobEnabled:job?!!job.enabled:null,entitiesEnabled:!!Scene.shouldRenderEntities,camera:{mode:String(Camera.mode),position:point(Camera.position),orientation:rotation(Camera.orientation),fieldOfView:Number(f.fieldOfView),aspectRatio:Number(f.aspectRatio)}};}
 function visuallyReady(d){var p=d.camera.position,q=d.camera.orientation;return d.connected&&d.serversExist&&d.entitiesEnabled&&d.resourceState===3&&d.renderJobAvailable&&d.renderJobEnabled&&d.renderMethod===jobMethod&&d.camera.mode==='independent'&&p&&q&&Math.abs(p.x-config.camera.x)<1e-5&&Math.abs(p.y-config.camera.y)<1e-5&&Math.abs(p.z-config.camera.z)<1e-5&&Math.abs(q.x)<1e-5&&Math.abs(q.y)<1e-5&&Math.abs(q.z)<1e-5&&Math.abs(Math.abs(q.w)-1)<1e-5&&isFinite(d.camera.fieldOfView)&&d.camera.fieldOfView>0;}
 function cleanup(){if(stopping)return;stopping=true;owned.forEach(function(id){if(String(Entities.getEntityProperties(id,['name']).name).indexOf(config.prefix)===0)Entities.deleteEntity(id);});report('cleanup-sent',{ownedCount:owned.length});}
 function select(name,mode){if(['opaque','mask'].indexOf(name)<0||['original','compressed'].indexOf(mode)<0)throw Error('Unsupported fixed Image case');current=name+'-'+mode;var source=config.assets[name][mode];resource=TextureCache.prefetch(source,0);finishedFrames=null;ready=false;Entities.editEntity(images[0],{visible:mode==='original',imageURL:config.assets[name].original});Entities.editEntity(images[1],{visible:mode==='compressed',imageURL:config.assets[name].compressed});report('case-applied',{sequence:sequence,name:name,mode:mode,emissive:emissive});}
 Window.stillSnapshotTaken.connect(function(filename){report('snapshot',{sequence:sequence,filename:String(filename)});});Script.scriptEnding.connect(cleanup);
 Audio.muted=true;MyAvatar.setGravity(0);MyAvatar.collisionsEnabled=false;Scene.shouldRenderAvatars=false;
 Snapshot.setSnapshotsLocation(config.outputDirectory);Snapshot.setSnapshotFormat('PNG');
 selectDrawStats();
 anchor();
 Script.setInterval(function(){
  Audio.muted=true;anchor();if(stopping)return;selectDrawStats();
  if(!initialized&&location.isConnected&&Entities.serversExist()){
   if(!Entities.canRez()){report('refused',{message:'The native observer does not have permission to create isolated fixtures.'});cleanup();Menu.triggerOption('Quit');return;}
   initialized=true;var background=add({name:'background',type:'Box',position:{x:config.center.x,y:config.center.y,z:config.center.z-.2},dimensions:{x:6,y:6,z:.05},color:{red:255,green:0,blue:255}});
   add({name:'background-material',type:'Material',parentID:background,materialURL:'materialData',priority:1,materialData:JSON.stringify({materialVersion:1,materials:{model:'hifi_pbr',albedo:[1,0,1],unlit:true}})});
   ['original','compressed'].forEach(function(mode){images.push(add({name:'image-'+mode,type:'Image',position:config.center,dimensions:{x:2,y:2,z:.01},imageURL:config.assets.opaque[mode],visible:mode==='original',emissive:emissive,keepAspectRatio:false}));});
   report('created',{ownedCount:owned.length,version:About.buildVersion});select('opaque','original');
  }
  if(!initialized)return;var d=diagnostic();if(Date.now()-lastDiagnostic>=1000){lastDiagnostic=Date.now();report('diagnostic',d);}
  if(resource&&resource.state===4){report('resource-error',{sequence:sequence,message:'Actual native texture loading failed',current:current});resource=null;}
  if(!visuallyReady(d)){finishedFrames=null;ready=false;}else if(finishedFrames===null)finishedFrames=frames;
  if(!ready&&finishedFrames!==null&&visuallyReady(d)&&frames-finishedFrames>=3){ready=true;report('native-ready',d);}
  if(pending){if(Date.now()-pending.started>=29000){report('snapshot-error',{sequence:pending.sequence,message:'Native texture/camera/GPU frames did not become ready before the unchanged deadline',diagnostic:d});pending=null;}else if(finishedFrames!==null&&visuallyReady(d)&&d.antialiasing.minimumSnapshotFrames!==null&&frames-Math.max(pending.frames,finishedFrames)>=d.antialiasing.minimumSnapshotFrames){var capture=pending;pending=null;report('snapshot-ready',{sequence:capture.sequence,diagnostic:d});Window.takeSnapshot(false,false,0,'image-case-'+capture.sequence+'.png');}}
  var request=new XMLHttpRequest();request.open('GET',config.commandURL+'?t='+Date.now());request.onreadystatechange=function(){
   if(request.readyState!==4||request.status!==200||stopping)return;var command;try{command=JSON.parse(request.responseText);}catch(error){return;}
   if(!command.sequence||command.sequence<=sequence)return;sequence=command.sequence;
   if(command.action==='cleanup'){cleanup();Script.setTimeout(function(){Menu.triggerOption('Quit');},1000);return;}
   if(command.action==='case'){select(command.name,command.mode);anchor();}
   else if(command.action==='snapshot'){anchor();pending={sequence:sequence,started:Date.now(),frames:frames};}
  };request.send();
 },250);
 Script.setTimeout(function(){cleanup();Menu.triggerOption('Quit');},350000);
 report('started',{version:About.buildVersion});
}());
