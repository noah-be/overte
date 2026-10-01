// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted helper loaded into one dedicated native gateway worker. QtScript ES5.
function createBrowserTablet(config) {
    'use strict';
    var tablet=Tablet.getTablet('com.highfidelity.interface.tablet.system');
    var helper=new OverlayWindow({title:'Browser tablet capture helper',source:config.qmlURL,width:120,height:80,visible:false});
    var approved=false,revision=0,visible=false,closed=false,pending=0,sequence=0,lastScreen='Home',loading=false;
    var deadline=0,lastError='',interval,captureFailed=false,grabbing=null,firstFrame=true,retryCapture=false;
    var renderJobs=[];
    // This worker supplies protocol, audio and Qt apps. The visitor renders all
    // world geometry locally; avoid rendering a second heavy 3D world here.
    // Keep the main view and its HUD/QML jobs running for grabToImage().
    if(typeof Render!=='undefined'&&typeof Render.getConfig==='function'){
        ['DrawOpaqueDeferred','DrawTransparentDeferred','DrawOpaques','DrawTransparents'].forEach(function(name){
            try{var job=Render.getConfig('RenderMainView.'+name);
                if(job&&typeof job.enabled==='boolean'){renderJobs.push({job:job,enabled:job.enabled});job.enabled=false;}
            }catch(error){/* A release exposes either the deferred or forward jobs. */}
        });
    }
    var snapshotRequest=0,snapshotSequence=0,outbox=[],chatObserver;
    function effects(){var result={muted:!!Audio.muted};if(typeof Users!=='undefined'&&typeof Users.getIgnoreRadiusEnabled==='function')result.shield=!!Users.getIgnoreRadiusEnabled();return result;}
    function send(value){
        if(closed||!approved||!revision)return;value.type='tablet';value.revision=revision;
        // A Qt UI callback may run outside the engine-owned WebSocket thread.
        // Reuse its existing engine timer; do not create a QTimer in that callback.
        if(value.kind==='state')outbox=outbox.filter(function(item){return item.kind!=='state';});
        if(outbox.length>=32){var index=0;while(index<outbox.length&&outbox[index].kind==='frameReady')index++;outbox.splice(index===outbox.length?0:index,1);}
        outbox.push(value);
    }
    function flush(){var ready=outbox;outbox=[];ready.forEach(function(value){if(!closed&&approved&&revision===value.revision)config.send(value);});}
    function state(){send({kind:'state',visible:visible,screen:lastScreen,loading:loading,effects:effects()});}
    function cancelCapture(){
        if(grabbing){grabbing.cancelled=true;helper.sendToQml({kind:'cancelCapture'});}
        pending=0;retryCapture=true;if(!grabbing)captureFailed=false;
    }
    function home(){tablet.loadQMLSource('hifi/tablet/TabletHome.qml');lastScreen='Home';
        Script.setTimeout(function(){if(!closed&&visible&&approved)helper.sendToQml({kind:'focusTablet'});},150);}
    function screenChanged(kind,url){
        lastScreen=String(kind||'Tablet');loading=false;
        // Native desktop mode closes its loader on Home; present the actual existing
        // home QML with its real default-script buttons instead of inventing a menu.
        if(visible&&kind==='Home'&&!url)home();
        state();
    }
    function fromQml(message){
        if(closed)return;
        if(message.kind==='frame'&&grabbing&&message.sequence===grabbing.sequence&&message.revision===grabbing.revision){
            var capture=grabbing;grabbing=null;
            if(capture.cancelled||!approved||message.revision!==revision||message.cancelled){
                if(retryCapture){retryCapture=false;captureFailed=false;}return;
            }
            if(message.saved){firstFrame=false;loading=false;var rect=message.tabletRect;
                // Qt QVariant/QJSValue wrappers must not cross JSON serialization.
                var bounds=rect?{x:Number(rect.x),y:Number(rect.y),width:Number(rect.width),height:Number(rect.height)}:undefined;
                send({kind:'frameReady',sequence:Number(message.sequence),width:Number(message.width),height:Number(message.height),surface:String(message.surface),tabletRect:bounds,effects:effects()});lastError='';}
            else {pending=0;send({kind:'error',message:'The native tablet frame could not be saved.'});}
        }else if(message.kind==='clipboard'&&approved&&message.revision===revision){
            send({kind:'clipboard',requestId:Number(message.requestId),text:String(message.text||'')});
        }else if(message.kind==='error'&&approved&&message.revision===revision){
            // The synchronous QML capture rejection has no outstanding GPU grab.
            if(message.operation==='capture'){grabbing=null;pending=0;}loading=false;
            if(message.message!==lastError){lastError=message.message;send({kind:'error',message:message.message});}
        }
    }
    function muteChanged(){if(visible&&approved)send({kind:'microphone',muted:!!Audio.muted});}
    function snapshotMessage(channel,text,sender,localOnly){
        if(closed||!approved||channel!==config.snapshotChannel||!localOnly)return;
        var message;try{message=JSON.parse(text);}catch(error){return;}
        if(message.kind!=='request'||snapshotRequest)return;
        snapshotRequest=++snapshotSequence;cancelCapture();visible=false;helper.sendToQml({kind:'hide'});state();
        send({kind:'snapshot',requestId:snapshotRequest,animated:!!message.animated,aspectRatio:1.91});
    }
    if(config.snapshotChannel){Messages.subscribe(config.snapshotChannel);Messages.messageReceived.connect(snapshotMessage);}
    if(config.chatURL){Script.include(config.chatURL);chatObserver=createBrowserTabletChat({isActive:function(){return !closed&&approved&&visible;},send:send});}
    helper.fromQml.connect(fromQml);tablet.screenChanged.connect(screenChanged);
    if(Audio.mutedChanged)Audio.mutedChanged.connect(muteChanged);
    // Load the actual version-matched installed defaults alongside the browser
    // bridge. This supplies every standard tablet app and its existing behavior.
    if(config.filesDirectory&&typeof Snapshot!=='undefined'&&typeof Snapshot.setSnapshotsLocation==='function')Snapshot.setSnapshotsLocation(config.filesDirectory);
    Script.load(config.defaultScriptsURL);
    tablet.toolbarMode=true;
    interval=Script.setInterval(function(){
        flush();
        if(closed||!visible||!approved||captureFailed)return;
        if(grabbing||pending){
            if(Date.now()<deadline)return;
            cancelCapture();retryCapture=false;captureFailed=true;loading=false;
            send({kind:'error',message:'The native tablet did not finish drawing within '+(firstFrame?'30':'8')+' seconds. Use Home after loading completes, or reconnect to retry.'});
            state();return;
        }
        pending=++sequence;deadline=Date.now()+(firstFrame?30000:8000);
        grabbing={revision:revision,sequence:pending,cancelled:false};
        helper.sendToQml({kind:'capture',path:config.framePath+'.'+revision+'.'+pending+'.png',revision:revision,sequence:pending});
    },150);
    return {
        setAuthority:function(nextRevision,allowed){
            if(revision!==nextRevision||approved!==!!allowed){cancelCapture();outbox=[];revision=nextRevision;approved=!!allowed;lastError='';snapshotRequest=0;firstFrame=true;
                if(!approved){visible=false;helper.sendToQml({kind:'hide'});}else state();}
        },
        receive:function(message){
            if(closed||!approved||message.revision!==revision)return;
            if(message.action==='open'){visible=true;loading=true;cancelCapture();tablet.toolbarMode=true;home();state();}
            else if(message.action==='close'){visible=false;cancelCapture();helper.sendToQml({kind:'hide'});state();}
            else if(message.action==='home'&&visible){cancelCapture();home();state();}
            else if(message.action==='back'&&visible){cancelCapture();tablet.returnToPreviousApp();state();}
            else if(message.action==='frameAck'&&message.frameSequence===pending)pending=0;
            else if(message.action==='snapshotResult'&&message.requestId===snapshotRequest){
                snapshotRequest=0;visible=true;state();
                Messages.sendLocalMessage(config.snapshotChannel,JSON.stringify({kind:'result',stillPath:message.stillPath,gifPath:message.gifPath,error:message.error}));
                Script.setTimeout(function(){if(!closed&&approved)helper.sendToQml({kind:'focusTablet'});},750);
            }
            else if(message.action==='input'&&visible){message.kind='input';helper.sendToQml(message);}
        },
        close:function(){if(closed)return;closed=true;visible=false;outbox=[];Script.clearInterval(interval);
            if(chatObserver)chatObserver.close();
            helper.fromQml.disconnect(fromQml);tablet.screenChanged.disconnect(screenChanged);
            if(config.snapshotChannel){Messages.messageReceived.disconnect(snapshotMessage);Messages.unsubscribe(config.snapshotChannel);}
            if(Audio.mutedChanged)Audio.mutedChanged.disconnect(muteChanged);helper.close();
            renderJobs.forEach(function(saved){saved.job.enabled=saved.enabled;});renderJobs=[];}
    };
}
