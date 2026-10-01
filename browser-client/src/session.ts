// SPDX-License-Identifier: Apache-2.0
import type { Avatar, Entity, Pose, Quat, Vec3 } from './world-data';
import { parseTabletMessage, type TabletMessage } from './tablet-protocol';
import { defaultAvatarAsset } from './default-avatar';
import {validateVisitorPreferences,type VisitorPreferences} from '../shared/visitor-preferences.mjs';
import {validateVisitorPersona,type VisitorPersona} from '../shared/visitor-persona.mjs';

export type ServerMessage =
    | TabletMessage
    | {type:'state'; state:'connecting'|'connected'|'disconnected'|'error'; message?:string; sessionId?:string; permissionRevision?:number}
    | {type:'entities'; entities:Entity[]}
    | {type:'entityUpdates'; entities:Entity[]; removed:string[]}
    | {type:'avatars'; avatars:Avatar[]; selfId?:string}
    | {type:'pose'; position:Vec3; orientation?:Quat}
    | {type:'poseRequest'; nonce:string; permissionRevision:number; position:Vec3; orientation:Quat}
    | {type:'navigation'; nonce:string; permissionRevision:number; domain:string}
    | {type:'navigationHistory'; nonce:string; permissionRevision:number; direction:'back'|'forward'}
    | ({type:'visitorPreferences';permissionRevision:number} & VisitorPreferences)
    | ({type:'visitorPersona';permissionRevision:number} & VisitorPersona)
    | {type:'error'|'warning'; message:string}
    | {type:'interaction'; message:string; entityId?:string};

function isRecord(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === 'object' && !Array.isArray(value);
}
export function parseServerMessage(text: string): ServerMessage {
    if (text.length > 16 * 1024 * 1024) throw new Error('Gateway response too large');
    const value: unknown = JSON.parse(text);
    if (!isRecord(value) || typeof value.type !== 'string') throw new Error('Invalid gateway message');
    switch (value.type) {
        case 'tablet': return parseTabletMessage(value);
        case 'state':
            if (!['connecting','connected','disconnected','error'].includes(String(value.state))) throw new Error('Invalid connection state');
            if (value.sessionId !== undefined && (typeof value.sessionId !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(value.sessionId))) throw new Error('Invalid session identifier');
            if (value.permissionRevision !== undefined && (!Number.isSafeInteger(value.permissionRevision) || Number(value.permissionRevision) < 1)) throw new Error('Invalid session authority');
            break;
        case 'entities':
        case 'entityUpdates':
            if (!Array.isArray(value.entities) || value.entities.length > 100000 ||
                !value.entities.every(entity => isRecord(entity) && typeof entity.id === 'string' && typeof entity.type === 'string')) throw new Error('Invalid entity snapshot');
            if (value.type === 'entityUpdates' && (!Array.isArray(value.removed) || value.removed.length > 100000 || !value.removed.every(id => typeof id === 'string' && id.length <= 128))) throw new Error('Invalid entity deletions');
            break;
        case 'avatars':
            if (!Array.isArray(value.avatars) || value.avatars.length > 10000 ||
                !value.avatars.every(validAvatar)) throw new Error('Invalid avatar snapshot');
            break;
        case 'pose':
            if (!validPosition(value.position)) throw new Error('Invalid spawn position');
            break;
        case 'poseRequest':
            if (typeof value.nonce !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value.nonce)
                || !Number.isSafeInteger(value.permissionRevision) || Number(value.permissionRevision) < 1
                || !validPosition(value.position) || Object.values(value.position).some(axis => Math.abs(axis) >= 32768)
                || !validOrientation(value.orientation)) throw new Error('Invalid native navigation request');
            break;
        case 'navigation':
        case 'navigationHistory':
            if (typeof value.nonce !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value.nonce)
                || !Number.isSafeInteger(value.permissionRevision) || Number(value.permissionRevision) < 1) throw new Error('Invalid Places navigation authority');
            if (value.type === 'navigation') {
                if (typeof value.domain !== 'string' || value.domain.length > 1024) throw new Error('Invalid Places domain address');
                const address = new URL(value.domain);
                if (address.protocol !== 'overte:' || !address.hostname || address.username || address.password || address.hash || address.search) throw new Error('Invalid Places domain address');
            } else if (value.direction !== 'back' && value.direction !== 'forward') throw new Error('Invalid Places history direction');
            break;
        case 'visitorPreferences':
            if (!Number.isSafeInteger(value.permissionRevision) || Number(value.permissionRevision) < 1) throw new Error('Invalid visitor preference authority');
            return {type:'visitorPreferences',permissionRevision:Number(value.permissionRevision),...validateVisitorPreferences({bookmarks:value.bookmarks,...(value.home === undefined ? {} : {home:value.home})})};
        case 'visitorPersona': {
            if (!Number.isSafeInteger(value.permissionRevision) || Number(value.permissionRevision)<1) throw new Error('Invalid visitor avatar authority');
            const fields=Object.fromEntries(['displayName','avatarURL','avatarScale','avatarFavorites']
                .filter(key=>Object.hasOwn(value,key)).map(key=>[key,value[key]]));
            return {type:'visitorPersona',permissionRevision:Number(value.permissionRevision),...validateVisitorPersona(fields)};
        }
        case 'error':
        case 'warning':
        case 'interaction':
            if (typeof value.message !== 'string' || value.message.length > 4096) throw new Error('Invalid gateway notice');
            break;
        default: throw new Error('Unsupported gateway message');
    }
    if (value.message !== undefined && typeof value.message !== 'string') throw new Error('Invalid gateway notice');
    return value as ServerMessage;
}
function validPosition(value: unknown): value is Vec3 {
    return isRecord(value) && ['x','y','z'].every(axis => typeof value[axis] === 'number' && Number.isFinite(value[axis]));
}
function validOrientation(value: unknown): value is Quat {
    if (!isRecord(value) || !['x','y','z','w'].every(axis => typeof value[axis] === 'number' && Number.isFinite(value[axis]))) return false;
    const norm = Math.hypot(Number(value.x), Number(value.y), Number(value.z), Number(value.w));
    return norm > 0.99 && norm < 1.01;
}
function validAvatar(value:unknown):boolean {
    if (!isRecord(value) || typeof value.id !== 'string' || !validPosition(value.position)) return false;
    if (value.displayName !== undefined && (typeof value.displayName !== 'string' || value.displayName.length > 256)) return false;
    if (value.orientation !== undefined && !validOrientation(value.orientation)) return false;
    if (value.scale !== undefined && (typeof value.scale !== 'number' || !Number.isFinite(value.scale) || value.scale <= 0 || value.scale > 1000)) return false;
    if (value.skeletonModelURL !== undefined && (typeof value.skeletonModelURL !== 'string' || value.skeletonModelURL.length > 4096)) return false;
    if (value.skeletonOffset !== undefined && (!validPosition(value.skeletonOffset) || Object.values(value.skeletonOffset).some(axis => Math.abs(axis) > 100))) return false;
    if (value.jointNames === undefined) return value.jointRotations === undefined && value.jointTranslations === undefined;
    if (!Array.isArray(value.jointNames) || value.jointNames.length > 1000 || !value.jointNames.every(name => typeof name === 'string' && name.length > 0 && name.length <= 256)) return false;
    if (value.jointRotations !== undefined && (!Array.isArray(value.jointRotations) || value.jointRotations.length !== value.jointNames.length || !value.jointRotations.every(validOrientation))) return false;
    if (value.jointTranslations !== undefined && (!Array.isArray(value.jointTranslations) || value.jointTranslations.length !== value.jointNames.length || !value.jointTranslations.every(position => validPosition(position) && Object.values(position).every(axis => Math.abs(axis) < 1000000)))) return false;
    return true;
}

export interface SessionCallbacks {
    message: (message:ServerMessage) => void;
    audio: (data:ArrayBuffer) => void;
    closed: (reason:string) => void;
    error: (reason:string) => void;
}

export class BrowserSession {
    private socket?: WebSocket;
    private timeout?: ReturnType<typeof setTimeout>;
    private generation = 0;
    sessionId = '';
    connected = false;
    private lastPose = 0;

    constructor(private callbacks:SessionCallbacks) {}

    join(domain:string, displayName:string, visitorPreferences?:VisitorPreferences, visitorPersona?:VisitorPersona): void {
        const payload=JSON.stringify({type:'join',domain,displayName,
            ...(visitorPreferences ? {visitorPreferences:validateVisitorPreferences(visitorPreferences)} : {}),
            ...(visitorPersona ? {visitorPersona:validateVisitorPersona(visitorPersona)} : {})});
        if (new TextEncoder().encode(payload).length>192*1024) throw new Error('Your combined join address and visitor preferences exceed the 192 KiB session limit.');
        this.leave();
        const generation = ++this.generation;
        const url = new URL('/session', window.location.href);
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(url);
        this.socket = socket;
        socket.binaryType = 'arraybuffer';
        this.timeout = setTimeout(() => {
            if (generation !== this.generation || this.connected) return;
            this.callbacks.error('Connection timed out. Check the domain address and gateway, then try again.');
            socket.close();
        }, 90000);
        socket.onopen = () => {
            if (generation === this.generation) socket.send(payload);
        };
        socket.onmessage = event => {
            if (generation !== this.generation) return;
            if (event.data instanceof ArrayBuffer) {
                if (event.data.byteLength <= 384000 && event.data.byteLength % 4 === 0) this.callbacks.audio(event.data);
                return;
            }
            try {
                const message = parseServerMessage(event.data);
                if (message.type === 'state') {
                    if (message.sessionId) this.sessionId = message.sessionId;
                    this.connected = message.state === 'connected';
                    if (this.connected) clearTimeout(this.timeout);
                }
                this.callbacks.message(message);
            } catch (error) {
                this.callbacks.error(`Gateway protocol error: ${error instanceof Error ? error.message : String(error)}`);
                // The browser API forbids protocol-reserved codes such as
                // 1002. Use an application code so rejection still tears down
                // the owned session (https://websockets.spec.whatwg.org/#dom-websocket-close).
                socket.close(4002, 'Protocol error');
            }
        };
        socket.onerror = () => {
            if (generation === this.generation) this.callbacks.error('Gateway unavailable. Start the gateway or check your connection.');
        };
        socket.onclose = event => {
            if (generation !== this.generation) return;
            clearTimeout(this.timeout);
            this.connected = false;
            this.sessionId = '';
            this.callbacks.closed(event.reason || 'Connection closed. You can join again.');
        };
    }

    send(message:unknown): void {
        if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message));
    }
    sendPose(pose:Pose): void {
        if (!this.connected || performance.now() - this.lastPose < 32) return;
        this.lastPose = performance.now();
        this.send({type:'pose', ...pose});
    }
    sendAudio(data:ArrayBuffer): void {
        if (this.connected && this.socket?.readyState === WebSocket.OPEN && this.socket.bufferedAmount < 19200) this.socket.send(data);
    }
    assetURL(asset:string): string {
        const bundled = defaultAvatarAsset(asset,window.location.href);
        if (bundled) return bundled;
        if (!this.sessionId) throw new Error('Asset session is not ready');
        const url = new URL(`/api/assets/${encodeURIComponent(this.sessionId)}`, window.location.href);
        url.searchParams.set('url', asset);
        return url.href;
    }
    leave(): void {
        this.generation++;
        clearTimeout(this.timeout);
        this.send({type:'leave'});
        this.socket?.close(1000, 'Left domain');
        this.socket = undefined;
        this.sessionId = '';
        this.connected = false;
    }
}
