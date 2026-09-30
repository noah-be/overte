// SPDX-License-Identifier: Apache-2.0
import type { Avatar, Entity, Pose, Quat, Vec3 } from './world-data';

export type ServerMessage =
    | {type:'state'; state:'connecting'|'connected'|'disconnected'|'error'; message?:string; sessionId?:string}
    | {type:'entities'; entities:Entity[]}
    | {type:'avatars'; avatars:Avatar[]; selfId?:string}
    | {type:'pose'; position:Vec3; orientation?:Quat}
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
        case 'state':
            if (!['connecting','connected','disconnected','error'].includes(String(value.state))) throw new Error('Invalid connection state');
            if (value.sessionId !== undefined && (typeof value.sessionId !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(value.sessionId))) throw new Error('Invalid session identifier');
            break;
        case 'entities':
            if (!Array.isArray(value.entities) || value.entities.length > 100000 ||
                !value.entities.every(entity => isRecord(entity) && typeof entity.id === 'string' && typeof entity.type === 'string')) throw new Error('Invalid entity snapshot');
            break;
        case 'avatars':
            if (!Array.isArray(value.avatars) || value.avatars.length > 10000 ||
                !value.avatars.every(avatar => isRecord(avatar) && typeof avatar.id === 'string' && validPosition(avatar.position))) throw new Error('Invalid avatar snapshot');
            break;
        case 'pose':
            if (!validPosition(value.position)) throw new Error('Invalid spawn position');
            break;
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

    join(domain:string, displayName:string): void {
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
            if (generation === this.generation) socket.send(JSON.stringify({type:'join', domain, displayName}));
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
                socket.close(1002, 'Protocol error');
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
