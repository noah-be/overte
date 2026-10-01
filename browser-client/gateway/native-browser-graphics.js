// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted QtScript ES5 adapter for the version-matched real Settings app.
function createBrowserGraphics(config){
    'use strict';
    var approved=false,revision=0,closed=false,nextRequest=0,pending=null,state=null,lastMessage='',pageSeen=false,uiSequence=0;
    function validState(value){return value&&value.version===1&&typeof value.localLights==='boolean'&&typeof value.cameraClipping==='boolean'&&validChange('fieldOfView',value.fieldOfView)&&validChange('resolutionPercent',value.resolutionPercent)&&Object.keys(value).length===5;}
    function validChange(field,value){if(field==='fieldOfView')return typeof value==='number'&&value%1===0&&value>=20&&value<=130;if(field==='resolutionPercent')return typeof value==='number'&&value%10===0&&value>=10&&value<=200;return (field==='localLights'||field==='cameraClipping')&&typeof value==='boolean';}
    function clone(value){return {version:1,fieldOfView:value.fieldOfView,resolutionPercent:value.resolutionPercent,localLights:value.localLights,cameraClipping:value.cameraClipping};}
    function ui(message){if(closed||uiSequence>=9007199254740991)return;Messages.sendLocalMessage(config.channel,JSON.stringify({kind:'effective',sequence:++uiSequence,revision:revision,ready:approved&&!!state&&!pending,settings:state?clone(state):{version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true},message:message||''}));}
    function request(operation,field,value){
        if(closed||!approved||pending)return;
        if(nextRequest>=9007199254740991){ui('Reconnect to continue changing graphics settings.');return;}
        pending={id:++nextRequest,revision:revision,deadline:config.now()+8000};
        var message={kind:'graphics',schemaVersion:1,requestId:pending.id,operation:operation};
        if(operation==='change'){message.field=field;message.value=value;}
        config.send(message);ui('Applying browser graphics settings…');
    }
    function received(channel,text,sender,localOnly){
        if(closed||channel!==config.channel||!localOnly||typeof text!=='string'||text.length>4096)return;
        var value;try{value=JSON.parse(text);}catch(error){return;}
        if(!value||typeof value!=='object'||value instanceof Array)return;
        if(value.kind==='ready')pageSeen=true;
        if(!approved)return;
        if(value.kind==='ready'){if(pending)ui('Applying browser graphics settings…');else if(state)ui();else request('request');}
        else if(value.kind==='change'&&state&&!pending&&validChange(value.field,value.value)&&state[value.field]!==value.value)request('change',value.field,value.value);
    }
    function poll(){if(closed||!pending||config.now()<pending.deadline)return;pending=null;lastMessage='The browser did not confirm the graphics setting within 8 seconds. Reopen Settings to retry.';ui(lastMessage);}
    Messages.subscribe(config.channel);Messages.messageReceived.connect(received);
    return {
        setAuthority:function(nextRevision,allowed){if(closed)return;var valid=typeof nextRevision==='number'&&nextRevision%1===0&&nextRevision>=1&&nextRevision<=9007199254740991;var nextAllowed=allowed===true&&valid;nextRevision=valid?nextRevision:0;if(revision!==nextRevision||approved!==nextAllowed){revision=valid?nextRevision:0;approved=nextAllowed;pending=null;state=null;lastMessage='';if(approved&&pageSeen)request('request');else ui();}},
        receive:function(value){
            if(closed||!approved||!pending||!value||typeof value!=='object'||value.revision!==revision||pending.revision!==revision||value.action!=='graphicsResult'||value.schemaVersion!==1||value.requestId!==pending.id||typeof value.accepted!=='boolean'||!validState(value.settings)||(value.message!==undefined&&(typeof value.message!=='string'||value.message.length>512)))return;
            if(config.now()>=pending.deadline){poll();return;}
            state=clone(value.settings);pending=null;lastMessage=value.message||(value.accepted?'':'The browser could not apply that graphics setting.');ui(lastMessage);
        },
        poll:poll,
        close:function(){if(closed)return;closed=true;pending=null;state=null;Messages.messageReceived.disconnect(received);Messages.unsubscribe(config.channel);}
    };
}
