// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Engine-polled trusted adapter. Signal callbacks never send or create timers.
function createBrowserPushToTalk(config) {
    'use strict';
    var audio=config.audio, revision=0, approved=false, closed=false, armed=false, requested=false, sequence=0;
    var mode=null, dirty=true, lastState='', connections=[], scope='';
    function current(){return !closed&&approved&&revision>0&&config.current(revision)
        &&(typeof config.authority!=='function'||config.authority()===scope);}
    function changed(){dirty=true;}
    ['pushToTalkDesktopChanged','pushingToTalkChanged','mutedChanged'].forEach(function(name){
        var signal=audio[name];if(signal&&typeof signal.connect==='function'){signal.connect(changed);connections.push(signal);}
    });
    function release(){requested=false;audio.pushingToTalk=false;}
    function apply(){
        var enabled=audio.pushToTalkDesktop===true, held=current()&&armed&&enabled&&requested;
        // f91 Audio::handlePushedToTalk unmutes only after the real held flag.
        // Writing muted=false while not held would disable native Desktop PTT.
        audio.pushingToTalk=held;
        audio.muted=!current()||!armed||(enabled&&!held);
        dirty=true;
    }
    return {
        setAuthority:function(nextRevision, allowed){
            if(closed)return;
            var renew=revision!==nextRevision||!allowed||!approved;
            if(renew){release();armed=false;sequence=0;lastState='';mode=null;}
            revision=nextRevision;approved=allowed===true;
            if(approved&&renew&&typeof config.authority==='function'){scope=config.authority();if(typeof scope!=='string'||!scope.length||scope.length>4096)approved=false;}
            apply();
        },
        release:function(){if(!closed){release();apply();}},
        setMuted:function(muted){
            if(closed||typeof muted!=='boolean')return;
            armed=current()&&!muted;if(!armed)release();apply();
        },
        receive:function(message){
            if(!current()||message.type!=='pushToTalk'||message.version!==1||message.permissionRevision!==revision
                ||typeof message.held!=='boolean'||typeof message.sequence!=='number'||message.sequence%1!==0
                ||message.sequence!==sequence+1||message.sequence>9007199254740991||message.held&&message.sequence===9007199254740991)return;
            sequence=message.sequence;requested=message.held&&armed&&audio.pushToTalkDesktop===true;apply();
        },
        poll:function(){
            if(closed)return;
            if(!current()){if(approved||armed||requested){approved=false;release();armed=false;apply();}return;}
            var enabled=audio.pushToTalkDesktop===true;
            if(mode!==enabled){mode=enabled;release();if(enabled)apply();dirty=true;}
            if(!dirty)return;dirty=false;
            var value={type:'pushToTalkState',version:1,permissionRevision:revision,sequence:sequence,
                enabled:enabled,held:enabled&&audio.pushingToTalk===true,muted:audio.muted!==false};
            var signature=JSON.stringify(value);if(signature!==lastState&&current()){lastState=signature;config.send(value);}
        },
        close:function(){if(closed)return;release();armed=false;audio.muted=true;closed=true;approved=false;
            connections.forEach(function(signal){signal.disconnect(changed);});connections=[];lastState='';}
    };
}
