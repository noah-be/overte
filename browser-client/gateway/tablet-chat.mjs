// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export function nativeChatMessage(message){
    if(!Number.isSafeInteger(message.sequence)||message.sequence<1||!['local','domain'].includes(message.channel)||typeof message.text!=='string'||!message.text||Buffer.byteLength(message.text,'utf8')>8192||typeof message.displayName!=='string'||message.displayName.length>128||typeof message.senderId!=='string'||!/^\{?[a-f0-9-]{36}\}?$/i.test(message.senderId))throw Error('Invalid native chat observation');
    return {sequence:message.sequence,channel:message.channel,text:message.text,displayName:message.displayName,senderId:message.senderId};
}
