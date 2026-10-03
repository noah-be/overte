// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted helper loaded into one dedicated native gateway worker. QtScript ES5.
function createBrowserTablet(config) {
    'use strict';
    var tablet=Tablet.getTablet('com.highfidelity.interface.tablet.system');
    var helper=new OverlayWindow({title:'Browser tablet capture helper',source:config.qmlURL,width:120,height:80,visible:false});
    var approved=false,revision=0,visible=false,closed=false,pending=0,sequence=0,lastScreen='Home',loading=false;
    var deadline=0,lastError='',interval,captureFailed=false,grabbing=null,firstFrame=true,retryCapture=false;
    var navigationSequence=0;
    var helperReady=false,helperProbe=0,helperProbeSequence=0,firstDeadline=0;
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
    var worldKeyRequest=0,worldKeyReady=false;
    var snapshotRequest=0,snapshotSequence=0,outbox=[],chatObserver,graphics,browserCapture;
    function effects(){var result={muted:!!Audio.muted};if(typeof Users!=='undefined'&&typeof Users.getIgnoreRadiusEnabled==='function')result.shield=!!Users.getIgnoreRadiusEnabled();return result;}
    function send(value){
        if(closed||!approved||!revision)return;value.type='tablet';value.revision=revision;
        // A Qt UI callback may run outside the engine-owned WebSocket thread.
        // Reuse its existing engine timer; do not create a QTimer in that callback.
        if(value.kind==='state')outbox=outbox.filter(function(item){return item.kind!=='state';});
        if(outbox.length>=32){var index=0;while(index<outbox.length&&outbox[index].kind==='frameReady')index++;outbox.splice(index===outbox.length?0:index,1);}
        outbox.push(value);
    }
    function flush(){var ready=outbox;outbox=[];ready.forEach(function(value){if(!closed&&approved&&revision===value.revision&&(value.kind!=='capture'||value.navigationSequence===navigationSequence&&visible))config.send(value);});}
    function state(){send({kind:'state',visible:visible,screen:lastScreen,loading:loading,effects:effects()});}
    function captureTimeout(){
        cancelCapture();helperProbe=0;retryCapture=false;captureFailed=true;loading=false;
        send({kind:'error',message:'The native tablet did not finish drawing within '+(firstFrame?'30':'8')+' seconds. Use Home after loading completes, or reconnect to retry.'});
        state();
    }
    function cancelCapture(){
        if(captureFailed)firstDeadline=0;
        if(grabbing){grabbing.cancelled=true;helper.sendToQml({kind:'cancelCapture'});}
        pending=0;retryCapture=true;if(!grabbing)captureFailed=false;
    }
    function changeView(message){
        if(typeof message.navigationSequence!=='number'||message.navigationSequence%1!==0||message.navigationSequence<=navigationSequence||message.navigationSequence>9007199254740991)return false;
        navigationSequence=message.navigationSequence;worldKeyRequest=0;worldKeyReady=false;if(config.releasePushToTalk)config.releasePushToTalk();if(browserCapture)browserCapture.resetView();helper.sendToQml({kind:'resetInput'});cancelCapture();
        outbox=outbox.filter(function(value){return value.kind!=='frameReady'&&value.kind!=='clipboard';});return true;
    }
    function home(){tablet.loadQMLSource('hifi/tablet/TabletHome.qml');lastScreen='Home';
        Script.setTimeout(function(){if(!closed&&visible&&approved)helper.sendToQml({kind:'focusTablet'});},150);}
    function screenChanged(kind,url){
        if(browserCapture)browserCapture.screen(kind,url);
        lastScreen=String(kind||'Tablet');loading=false;
        // Native desktop mode closes its loader on Home; present the actual existing
        // home QML with its real default-script buttons instead of inventing a menu.
        if(visible&&kind==='Home'&&!url)home();
        state();
    }
    function fromQml(message){
        if(closed)return;
        if(message.kind==='worldKeyReady'){
            if(approved&&!visible&&message.revision===revision&&message.navigationSequence===navigationSequence&&worldKeyRequest&&message.requestId===worldKeyRequest&&typeof message.ready==='boolean'){worldKeyReady=message.ready;send({kind:'worldKeyReady',requestId:worldKeyRequest,navigationSequence:navigationSequence,ready:worldKeyReady});}return;
        }
        if(message.kind==='helperReady'){
            if(approved&&visible&&!captureFailed&&message.revision===revision&&helperProbe&&message.probe===helperProbe&&firstDeadline&&Date.now()<firstDeadline){helperReady=true;helperProbe=0;}
            return;
        }
        if(message.kind==='frame'&&grabbing&&message.sequence===grabbing.sequence&&message.revision===grabbing.revision&&message.navigationSequence===grabbing.navigationSequence){
            var capture=grabbing;grabbing=null;
            if(firstFrame&&firstDeadline&&Date.now()>=firstDeadline&&!capture.cancelled){captureTimeout();return;}
            if(capture.cancelled||!approved||message.revision!==revision||message.navigationSequence!==navigationSequence||message.cancelled){
                if(retryCapture){retryCapture=false;captureFailed=false;}return;
            }
            if(message.saved){firstFrame=false;firstDeadline=0;loading=false;var rect=message.tabletRect;
                // Qt QVariant/QJSValue wrappers must not cross JSON serialization.
                var bounds=rect?{x:Number(rect.x),y:Number(rect.y),width:Number(rect.width),height:Number(rect.height)}:undefined;
                send({kind:'frameReady',sequence:Number(message.sequence),navigationSequence:navigationSequence,width:Number(message.width),height:Number(message.height),surface:String(message.surface),tabletRect:bounds,effects:effects()});lastError='';}
            else {pending=0;send({kind:'error',message:'The native tablet frame could not be saved.'});}
        }else if(message.kind==='clipboard'&&approved&&message.revision===revision&&message.navigationSequence===navigationSequence){
            send({kind:'clipboard',requestId:Number(message.requestId),text:String(message.text||'')});
        }else if(message.kind==='error'&&approved&&message.revision===revision){
            // The synchronous QML capture rejection has no outstanding GPU grab.
            if(message.operation==='capture'){grabbing=null;pending=0;}loading=false;
            if(message.message!==lastError){lastError=message.message;send({kind:'error',message:message.message});}
        }
    }
    function muteChanged(){if(visible&&approved&&Audio.pushToTalkDesktop!==true)send({kind:'microphone',muted:!!Audio.muted});}
    function snapshotMessage(channel,text,sender,localOnly){
        if(closed||!approved||channel!==config.snapshotChannel||!localOnly)return;
        var message;try{message=JSON.parse(text);}catch(error){return;}
        if(message.kind!=='request'||snapshotRequest)return;
        snapshotRequest=++snapshotSequence;cancelCapture();visible=false;if(browserCapture)browserCapture.resetView();helper.sendToQml({kind:'hide'});state();
        send({kind:'snapshot',requestId:snapshotRequest,animated:!!message.animated,aspectRatio:1.91});
    }
    if(config.snapshotChannel){Messages.subscribe(config.snapshotChannel);Messages.messageReceived.connect(snapshotMessage);}
    if(config.chatURL){Script.include(config.chatURL);chatObserver=createBrowserTabletChat({isActive:function(){return !closed&&approved&&visible;},send:send});}
    if(config.graphics){Script.include(config.graphics.scriptURL);graphics=createBrowserGraphics({channel:config.graphics.channel,now:Date.now,send:send});}
    if(config.capture){Script.include(config.capture.scriptURL);browserCapture=createBrowserCapture({channel:config.capture.channel,qmlURL:config.capture.qmlURL,now:Date.now,send:send,current:function(){return !closed&&approved&&visible;},navigation:function(){return navigationSequence;}});}
    helper.fromQml.connect(fromQml);tablet.screenChanged.connect(screenChanged);
    if(Audio.mutedChanged)Audio.mutedChanged.connect(muteChanged);
    // Load the actual version-matched installed defaults alongside the browser
    // bridge. This supplies every standard tablet app and its existing behavior.
    if(config.filesDirectory&&typeof Snapshot!=='undefined'&&typeof Snapshot.setSnapshotsLocation==='function')Snapshot.setSnapshotsLocation(config.filesDirectory);
    // The installed Create app selects qml/Edit.qml from this preference, not
    // Tablet.toolbarMode. This is the dedicated worker's isolated settings file.
    // Set it before defaults start so Create never opens detached native windows
    // outside the owned tablet capture surface. Preserve the prior worker value.
    var desktopTabletBecomesToolbar=Settings.getValue('desktopTabletBecomesToolbar',true);
    Settings.setValue('desktopTabletBecomesToolbar',false);
    Script.load(config.defaultScriptsURL);
    tablet.toolbarMode=true;
    interval=Script.setInterval(function(){
        if(graphics)graphics.poll();
        if(browserCapture)browserCapture.poll();
        flush();
        if(closed||!visible||!approved||captureFailed)return;
        if(firstFrame&&!firstDeadline)firstDeadline=Date.now()+30000;
        if(!helperReady){
            if(Date.now()>=firstDeadline){captureTimeout();return;}
            // QmlWindow silently drops fromScript while its asynchronous source
            // has no dynamicContent. Reuse one bounded revision-bound probe until
            // that exact loaded helper acknowledges it; no GPU grab exists yet.
            if(!helperProbe)helperProbe=++helperProbeSequence;
            helper.sendToQml({kind:'readyProbe',revision:revision,probe:helperProbe});
            if(!helperReady)return;
        }
        if(grabbing||pending){
            if(Date.now()<deadline)return;
            captureTimeout();return;
        }
        if(firstFrame&&Date.now()>=firstDeadline){captureTimeout();return;}
        pending=++sequence;deadline=firstFrame?firstDeadline:Date.now()+8000;
        grabbing={revision:revision,sequence:pending,navigationSequence:navigationSequence,cancelled:false};
        helper.sendToQml({kind:'capture',path:config.framePath+'.'+revision+'.'+pending+'.png',revision:revision,sequence:pending,navigationSequence:navigationSequence});
    },150);
    return {
        setAuthority:function(nextRevision,allowed){
            if(revision!==nextRevision||approved!==!!allowed){helper.sendToQml({kind:'resetInput'});cancelCapture();outbox=[];worldKeyRequest=0;worldKeyReady=false;revision=nextRevision;navigationSequence=0;approved=!!allowed;lastError='';snapshotRequest=0;firstFrame=true;firstDeadline=0;helperReady=false;helperProbe=0;
                if(graphics)graphics.setAuthority(revision,approved);
                if(browserCapture)browserCapture.setAuthority(revision,approved);
                if(!approved||visible){visible=false;helper.sendToQml({kind:'hide'});}if(approved)state();}
        },
        receive:function(message){
            if(closed||!approved||message.revision!==revision)return;
            if(['graphicsResult','graphicsChange','graphicsCancel'].indexOf(message.action)!==-1&&graphics){graphics.receive(message);return;}
            if(message.action==='captureResult'&&browserCapture){browserCapture.receive(message);return;}
            if(message.action==='open'){if(!changeView(message))return;visible=true;loading=true;cancelCapture();tablet.toolbarMode=true;home();state();}
            else if(message.action==='close'){if(!changeView(message))return;visible=false;cancelCapture();firstDeadline=0;helperProbe=0;helper.sendToQml({kind:'hide'});state();}
            else if(message.action==='home'&&visible){if(!changeView(message))return;home();state();}
            else if(message.action==='back'&&visible){if(!changeView(message))return;tablet.returnToPreviousApp();state();}
            else if(message.action==='frameAck'&&message.frameSequence===pending&&message.navigationSequence===navigationSequence){
                if(message.displayed===true)helper.sendToQml({kind:'displayFrame',revision:revision,sequence:pending,navigationSequence:navigationSequence});
                pending=0;
            }
            else if(message.action==='snapshotResult'&&message.requestId===snapshotRequest){
                snapshotRequest=0;visible=true;state();
                Messages.sendLocalMessage(config.snapshotChannel,JSON.stringify({kind:'result',stillPath:message.stillPath,gifPath:message.gifPath,error:message.error}));
                Script.setTimeout(function(){if(!closed&&approved)helper.sendToQml({kind:'focusTablet'});},750);
            }
            else if(message.action==='worldKeyArm'&&!visible&&message.navigationSequence===navigationSequence){worldKeyRequest=message.sequence;worldKeyReady=false;helper.sendToQml({kind:'armWorldKey',revision:revision,navigationSequence:navigationSequence,requestId:worldKeyRequest});}
            else if(message.action==='worldKeyCancel'&&message.navigationSequence===navigationSequence){worldKeyRequest=0;worldKeyReady=false;helper.sendToQml({kind:'cancelWorldKey'});}
            else if(message.action==='worldKey'&&!visible&&worldKeyReady&&worldKeyRequest&&message.requestId===worldKeyRequest&&message.navigationSequence===navigationSequence&&message.key==='x'){helper.sendToQml({kind:'worldKey',revision:revision,navigationSequence:navigationSequence,requestId:worldKeyRequest,key:'x'});}
            else if(message.action==='input'&&visible&&message.navigationSequence===navigationSequence){message.kind='input';helper.sendToQml(message);}
        },
        close:function(){if(closed)return;closed=true;visible=false;worldKeyRequest=0;worldKeyReady=false;helper.sendToQml({kind:'cancelWorldKey'});outbox=[];Script.clearInterval(interval);
            if(graphics)graphics.close();
            if(browserCapture)browserCapture.close();
            if(chatObserver)chatObserver.close();
            helper.fromQml.disconnect(fromQml);tablet.screenChanged.disconnect(screenChanged);
            if(config.snapshotChannel){Messages.messageReceived.disconnect(snapshotMessage);Messages.unsubscribe(config.snapshotChannel);}
            if(Audio.mutedChanged)Audio.mutedChanged.disconnect(muteChanged);helper.close();
            Settings.setValue('desktopTabletBecomesToolbar',desktopTabletBecomesToolbar);
            renderJobs.forEach(function(saved){saved.job.enabled=saved.enabled;});renderJobs=[];}
    };
}
