// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {validateBrowserGraphicsRequest,type BrowserGraphicsRequest} from '../shared/browser-graphics.mjs';
export const MAX_TABLET_FRAME_BYTES = 4 * 1024 * 1024;
export type TabletMessage =
    | {type:'tablet'; kind:'state'; revision:number; visible:boolean; screen:string; loading:boolean; effects?:{muted?:boolean;shield?:boolean}}
    | {type:'tablet'; kind:'frame'; revision:number; navigationSequence:number; sequence:number; width:number; height:number; mime:'image/png'; data:string; surface:'tablet'|'dialogs'; tabletRect?:{x:number;y:number;width:number;height:number};effects?:{muted?:boolean;shield?:boolean}}
    | {type:'tablet'; kind:'error'; revision:number; message:string}
    | {type:'tablet';kind:'chat';revision:number;sequence:number;channel:'local'|'domain';text:string;displayName:string;senderId:string}
    | {type:'tablet';kind:'clipboard';revision:number;requestId:number;text:string}
    | {type:'tablet'; kind:'snapshot';revision:number;requestId:number;animated:boolean;aspectRatio:number}
    | {type:'tablet'; kind:'microphone'; revision:number; muted:boolean}
    | ({type:'tablet';kind:'graphics';revision:number}&BrowserGraphicsRequest);

export function parseTabletMessage(value:unknown):TabletMessage {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid tablet message');
    const item = value as Record<string,unknown>;
    if (item.type !== 'tablet' || !Number.isSafeInteger(item.revision) || Number(item.revision) < 1) throw new Error('Invalid tablet authority');
    if(item.effects!==undefined){const effects=item.effects as Record<string,unknown>;if(!effects||typeof effects!=='object'||['muted','shield'].some(key=>effects[key]!==undefined&&typeof effects[key]!=='boolean'))throw new Error('Invalid tablet effects');}
    switch (item.kind) {
        case 'state':
            if (typeof item.visible !== 'boolean' || typeof item.loading !== 'boolean' || typeof item.screen !== 'string' || item.screen.length > 256) throw new Error('Invalid tablet state');
            break;
        case 'frame':
            if (!Number.isSafeInteger(item.navigationSequence) || Number(item.navigationSequence)<1 || !Number.isSafeInteger(item.sequence) || Number(item.sequence) < 1 || !['width','height'].every(key => Number.isSafeInteger(item[key]) && Number(item[key]) > 0 && Number(item[key]) <= 2048) || item.mime !== 'image/png' || !['tablet','dialogs'].includes(String(item.surface)) || typeof item.data !== 'string' || item.data.length > Math.ceil(MAX_TABLET_FRAME_BYTES / 3) * 4 || !/^[A-Za-z0-9+/]+={0,2}$/.test(item.data)) throw new Error('Invalid tablet frame');
            if(item.tabletRect!==undefined){const rect=item.tabletRect as Record<string,unknown>;if(!rect||typeof rect!=='object'||!['x','y','width','height'].every(key=>typeof rect[key]==='number'&&Number.isFinite(rect[key])&&Math.abs(Number(rect[key]))<=4096)||Number(rect.width)<=0||Number(rect.height)<=0)throw new Error('Invalid tablet window rectangle');}
            break;
        case 'error':
            if (typeof item.message !== 'string' || item.message.length > 1024) throw new Error('Invalid tablet error');
            break;
        case 'microphone':
            if (typeof item.muted !== 'boolean') throw new Error('Invalid tablet microphone state');
            break;
        case 'chat':
            if(!Number.isSafeInteger(item.sequence)||Number(item.sequence)<1||!['local','domain'].includes(String(item.channel))||typeof item.text!=='string'||!item.text||new TextEncoder().encode(item.text).length>8192||typeof item.displayName!=='string'||item.displayName.length>128||typeof item.senderId!=='string'||!/^\{?[a-f0-9-]{36}\}?$/i.test(item.senderId))throw Error('Invalid tablet chat');
            break;
        case 'clipboard':
            if(!Number.isSafeInteger(item.requestId)||Number(item.requestId)<1||typeof item.text!=='string'||new TextEncoder().encode(item.text).length>65536)throw Error('Invalid tablet clipboard');
            break;
        case 'snapshot':
            if(!Number.isSafeInteger(item.requestId)||Number(item.requestId)<1||typeof item.animated!=='boolean'||typeof item.aspectRatio!=='number'||!Number.isFinite(item.aspectRatio)||item.aspectRatio<.1||item.aspectRatio>4)throw Error('Invalid tablet snapshot');
            break;
        case 'graphics':
            return {type:'tablet',kind:'graphics',revision:Number(item.revision),...validateBrowserGraphicsRequest(item)};
        default: throw new Error('Unsupported tablet message');
    }
    return item as TabletMessage;
}
