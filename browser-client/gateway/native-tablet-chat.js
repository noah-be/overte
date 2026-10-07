// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Observe the actual standard native chat app's message-mixer delivery.
// Sending remains entirely in that app; this helper grants no new operation.
function createBrowserTabletChat(config) {
    'use strict';
    var closed=false,sequence=0,windowStart=0,windowCount=0;
    function bytes(text){var count=0;for(var i=0;i<text.length;i++){var value=text.charCodeAt(i);if(value<128)count++;else if(value<2048)count+=2;else if(value>=0xd800&&value<=0xdbff&&i+1<text.length&&text.charCodeAt(i+1)>=0xdc00&&text.charCodeAt(i+1)<=0xdfff){count+=4;i++;}else count+=3;if(count>8192)return count;}return count;}
    function received(channel,text,sender,localOnly){
        if(closed||!config.isActive()||localOnly||channel!=='chat'||typeof text!=='string'||text.length>32768)return;
        var message;try{message=JSON.parse(text);}catch(error){return;}
        if(!message||message.action!=='send_chat_message'||message.forApp||typeof message.message!=='string'||!message.message||bytes(message.message)>8192)return;
        var scope=String(message.channel||'domain').toLowerCase();if(scope!=='domain'&&scope!=='local')return;
        if(scope==='local'){
            var position=message.position;
            if(!position||!['x','y','z'].every(function(key){return typeof position[key]==='number'&&isFinite(position[key]);})||Vec3.distance(MyAvatar.position,position)>20)return;
        }
        var id=String(sender);if(!/^\{?[a-f0-9-]{36}\}?$/i.test(id))return;
        var now=Date.now();if(now-windowStart>=1000){windowStart=now;windowCount=0;}if(++windowCount>16)return;
        config.send({kind:'chat',sequence:++sequence,channel:scope,text:message.message,displayName:String(message.displayName||'Visitor').slice(0,128),senderId:id});
    }
    Messages.subscribe('chat');Messages.messageReceived.connect(received);
    return {close:function(){if(closed)return;closed=true;Messages.messageReceived.disconnect(received);Messages.unsubscribe('chat');}};
}
