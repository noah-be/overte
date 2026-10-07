// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted fixture author for the isolated laboratory only. Config is prepended by its owner.
(function () {
    'use strict';
    var config = NATIVE_RENDER_FIXTURE, owned = [], sequence = 0, model, material, initialized = false, stopping = false;
    var pendingSnapshot = null, frames = 0, drawingJob = null, lastDiagnostic = 0, readyReported = false;
    function report(kind, data) { print('NATIVE_RENDER_FIXTURE ' + JSON.stringify({kind:kind, at:Date.now(), data:data})); }
    function vec(value) { return value ? {x:Number(value.x),y:Number(value.y),z:Number(value.z)} : null; }
    function quat(value) { return value ? {x:Number(value.x),y:Number(value.y),z:Number(value.z),w:Number(value.w)} : null; }
    function numeric(value) { var number=Number(value);return isFinite(number)?number:null; }
    function anchor() {
        if(!location.isConnected||!Entities.serversExist())return;
        // Entity streaming initially follows the avatar-centered 10 m sphere,
        // independently of the visual camera. Move only this owned observer.
        MyAvatar.position=config.camera;MyAvatar.velocity={x:0,y:0,z:0};
        Camera.mode='independent';Camera.position=config.camera;Camera.lookAt(config.center);
        // Camera.lookAt changes _orientation without recompose(). The explicit
        // setter makes the transform used by the actual GPU view consistent.
        Camera.orientation=quat(Camera.orientation);
    }
    function diagnostics() {
        var result={connected:!!location.isConnected,serversExist:Entities.serversExist(),canRez:Entities.canRez(),
            shouldRenderEntities:!!Scene.shouldRenderEntities,shouldRenderAvatars:!!Scene.shouldRenderAvatars,
            avatarPosition:vec(MyAvatar.position),camera:{mode:String(Camera.mode),position:vec(Camera.position),orientation:quat(Camera.orientation)},
            modelLoaded:false,graphicsMeshes:[],renderFrames:frames,renderJobAvailable:!!drawingJob,
            renderJobEnabled:drawingJob?!!drawingJob.enabled:null,renderJobDrawn:drawingJob?numeric(drawingJob.numDrawn):null,renderRate:numeric(Stats.renderrate)};
        if(!model)return result;
        result.modelLoaded=Entities.isLoaded(model);
        var properties=Entities.getEntityProperties(model,['naturalDimensions','dimensions','position','rotation','registrationPoint','visible','entityHostType']);
        result.model={naturalDimensions:vec(properties.naturalDimensions),dimensions:vec(properties.dimensions),position:vec(properties.position),rotation:quat(properties.rotation),registrationPoint:vec(properties.registrationPoint),visible:!!properties.visible,hostType:String(properties.entityHostType)};
        if(!result.modelLoaded)return result;
        try{var graphics=Graphics.getModel(model);result.graphicsNumMeshes=graphics?numeric(graphics.numMeshes):0;
            var meshes=graphics&&graphics.meshes||[];for(var i=0;i<meshes.length&&i<64;i++)result.graphicsMeshes.push({numVertices:numeric(meshes[i].numVertices),numIndices:numeric(meshes[i].numIndices),numParts:numeric(meshes[i].numParts)});
        }catch(error){result.graphicsError=true;}
        return result;
    }
    function visuallyReady(state) {
        if(!state.modelLoaded||!state.shouldRenderEntities||state.camera.mode!=='independent'||!state.graphicsMeshes.length||!state.renderJobAvailable||!state.renderJobEnabled||state.renderFrames<1)return false;
        var p=state.camera.position,q=state.camera.orientation;
        if(!p||Math.abs(p.x-config.camera.x)>1e-5||Math.abs(p.y-config.camera.y)>1e-5||Math.abs(p.z-config.camera.z)>1e-5||!q||Math.abs(q.x)>1e-5||Math.abs(q.y)>1e-5||Math.abs(q.z)>1e-5||Math.abs(Math.abs(q.w)-1)>1e-5)return false;
        return state.graphicsMeshes.some(function(mesh){return mesh.numVertices===6&&mesh.numIndices===6&&mesh.numParts>0;});
    }
    function entity(properties) { properties.name = config.prefix + properties.name; properties.lifetime = 240; properties.collisionless = true; var id=Entities.addEntity(properties); if(String(id).replace(/[{}-]/g,'')==='00000000000000000000000000000000')throw Error('Actual native entity creation was refused'); owned.push(id); return id; }
    function cleanup() {
        if(stopping)return;stopping=true;
        owned.forEach(function(id){if(String(Entities.getEntityProperties(id,['name']).name).indexOf(config.prefix)===0)Entities.deleteEntity(id);});
        report('cleanup-sent',{ownedCount:owned.length});
    }
    Window.stillSnapshotTaken.connect(function(filename){ report('snapshot',{filename:String(filename),sequence:sequence}); });
    Script.scriptEnding.connect(cleanup);
    Audio.muted = true; Render.viewportResolutionScale = 1; MyAvatar.setGravity(0); MyAvatar.collisionsEnabled = false;
    Snapshot.setSnapshotsLocation(config.outputDirectory); Snapshot.setSnapshotFormat('PNG');
    // This observer compares entity pixels only, matching the browser fixture,
    // which never adds avatar meshes. Entity rendering is deliberately untouched.
    Scene.shouldRenderAvatars=false;
    try{drawingJob=Render.getConfig('RenderMainView.DrawTransparentDeferred');
        if(drawingJob&&drawingJob.newStats&&typeof drawingJob.newStats.connect==='function')drawingJob.newStats.connect(function(){frames++;});
        else drawingJob=null;
    }catch(error){drawingJob=null;}
    anchor();
    Script.setInterval(function(){
        Audio.muted=true;anchor();
        if(!initialized && location.isConnected && Entities.serversExist() && Entities.canRez()) {
            initialized=true;
            var background=entity({name:'background',type:'Box',position:{x:config.center.x,y:config.center.y,z:config.center.z-.2},dimensions:{x:6,y:6,z:.05},color:{red:0,green:0,blue:0}});
            entity({name:'background-material',type:'Material',parentID:background,materialURL:'materialData',priority:1,materialData:JSON.stringify({materialVersion:1,materials:{model:'hifi_pbr',albedo:[0,0,0],unlit:true}})});
            model=entity({name:'model',type:'Model',modelURL:config.modelURL,position:config.center,dimensions:{x:2,y:2,z:.1}});
            material=entity({name:'material',type:'Material',parentID:model,materialURL:'materialData',priority:1,materialData:JSON.stringify({materialVersion:1,materials:{model:'hifi_pbr',albedo:[1,1,1],unlit:true,opacity:.5,cullFaceMode:'CULL_NONE'}})});
            report('created',{ownedCount:owned.length,version:About.buildVersion,connected:!!location.isConnected,serversExist:Entities.serversExist(),canRez:Entities.canRez()});
        }
        if(!initialized||stopping)return;
        var state=diagnostics();
        if(Date.now()-lastDiagnostic>=1000){lastDiagnostic=Date.now();report('diagnostic',state);}
        if(!readyReported&&visuallyReady(state)){readyReported=true;report('native-ready',state);}
        if(pendingSnapshot){
            if(Date.now()-pendingSnapshot.started>=29000){report('snapshot-error',{sequence:pendingSnapshot.sequence,message:'Native model/camera/render-frame readiness did not stabilize before the existing snapshot deadline',diagnostic:state});pendingSnapshot=null;}
            else if(visuallyReady(state)&&frames-pendingSnapshot.frames>=3){
                var capture=pendingSnapshot;pendingSnapshot=null;report('snapshot-ready',{sequence:capture.sequence,diagnostic:state});
                Window.takeSnapshot(false,false,0,'case-'+capture.sequence+'.png');
            }
        }
        var request=new XMLHttpRequest();request.open('GET',config.commandURL+'?t='+Date.now());
        request.onreadystatechange=function(){
            if(request.readyState!==4||request.status!==200||stopping)return;
            var command;try{command=JSON.parse(request.responseText);}catch(e){return;}
            if(!command.sequence||command.sequence<=sequence)return;sequence=command.sequence;
            if(command.action==='cleanup'){cleanup();Script.setTimeout(function(){Menu.triggerOption('Quit');},1000);return;}
            if(command.action==='case' && ['CULL_NONE','CULL_FRONT','CULL_BACK'].indexOf(command.cull)>=0 && ['blend','mask','opaque'].indexOf(command.mode)>=0){
                var definition={model:'hifi_pbr',albedo:[1,1,1],unlit:true,cullFaceMode:command.cull,opacity:command.mode==='blend'?.5:1};
                if(command.mode==='mask'){definition.albedoMap=config.maskURL;definition.opacityMap=config.maskURL;definition.opacityMapMode='OPACITY_MAP_MASK';definition.opacityCutoff=.5;}
                Entities.editEntity(material,{materialData:JSON.stringify({materialVersion:1,materials:definition})});
                anchor();
                report('case-applied',{sequence:sequence,cull:command.cull,mode:command.mode});
            }
            if(command.action==='snapshot'){
                anchor();pendingSnapshot={sequence:sequence,started:Date.now(),frames:frames};
            }
        };request.send();
    },250);
    Script.setTimeout(function(){cleanup();Menu.triggerOption('Quit');},230000);
    report('started',{version:About.buildVersion});
}());
