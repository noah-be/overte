// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Latest complete avatar snapshot scheduling; other message kinds keep their sender.
// One physical write and one newest COMPLETE unsent JSON snapshot per socket.
export const MAX_BUFFER = 4 * 1024 * 1024;
export const MAX_TEXT_BYTES = 48 * 1024 * 1024 + 1024; // existing native ingress + session envelope
export const MAX_TEXT_CODE_UNITS = 16 * 1024 * 1024; // frontend text.length, not UTF-8 bytes
const channels=new WeakMap();
export class AvatarSnapshotSender {
    constructor(socket, currentOwner, observe = () => {}, onError = () => {}, onFlow) {
        if(channels.has(socket))throw Error('avatar-channel-already-owned');
        channels.set(socket,this);
        this.socket=socket;this.currentOwner=currentOwner;this.observe=observe;this.onError=onError;
        this.pending=null;this.flight=null;this.pumping=false;this.epoch=0;this.closed=false;this.observationRefused=false;
        if(typeof onFlow==='function')this.onFlow=onFlow;
    }
    authority(owner) {
        try {
            if(this.closed || this.currentOwner()!==owner || owner.closed || !owner.permissionsApproved
                || owner.browser!==this.socket || !owner.native || !Number.isSafeInteger(owner.permissionRevision)
                || owner.permissionRevision<1 || !owner.isCurrent())return null;
            return {owner,native:owner.native,revision:owner.permissionRevision,epoch:this.epoch};
        }catch{return null;}
    }
    valid(item) {
        const current=this.authority(item.owner);
        return current && current.native===item.native && current.revision===item.revision
            && current.epoch===item.epoch;
    }
    flow(event, value) {try{return this.onFlow?.(event,value);}catch{return null;}}
    offer(owner, value, at) {
        if(this.onFlow)this.flow('offer-enter',{owner,at});
        try {
        const epoch=this.epoch,authority=this.authority(owner);
        if(!authority || epoch!==this.epoch){if(this.onFlow)this.flow('offer-refused',{owner,at});return false;}
        if(value?.type!=='avatars' || !Number.isSafeInteger(at) || at<0)throw Error('avatar-offer-refused');
        let distance=null;
        const text=avatarSnapshotText(value,this.onFlow ? captured=>{distance=this.flow('capture',{owner,captured});} : undefined),size=Buffer.byteLength(text);
        if(!this.valid(authority)){if(this.onFlow)this.flow('offer-refused',{owner,at});return false;}
        // Serialized bytes cannot retain a mutable caller pose reference.
        this.pending={...authority,text,size,at};
        if(this.onFlow){if(distance!==undefined)this.pending.flowDistance=typeof distance==='number' && Number.isFinite(distance) && distance>=0 && distance<=300000?distance:null;this.flow('offer-validated',this.pending);}
        this.pump();return true;
        }catch(error){if(this.onFlow)this.flow('offer-threw',{owner,at});throw error;}
    }
    record(value) {try{this.observe(value);}catch{this.observationRefused=true;}}
    pump() {
        if(this.pumping)return;
        this.pumping=true;
        try {
        if(this.closed || this.flight || !this.pending)return;
        const item=this.pending;
        if(!this.valid(item)){if(this.pending===item)this.pending=null;return;}
        if(this.pending!==item)return; // a reentrant offer superseded this value
        const open=this.socket.readyState===1,bytes=open?this.socket.bufferedAmount:null;
        if(!open){this.pending=null;this.record({owner:item.owner,text:item.text,at:item.at,open,bytes,writeInvoked:false});return;}
        if(!this.valid(item)){if(this.pending===item)this.pending=null;return;}
        if(this.pending!==item)return;
        if(!(bytes<MAX_BUFFER)){
            // Keep latest complete snapshot. No timer or independent retry.
            this.record({owner:item.owner,text:item.text,at:item.at,open,bytes,writeInvoked:false});return;
        }
        this.pending=null;const token={item};this.flight=token;
        try {
            this.socket.send(item.text,error=>{
                if(this.flight!==token)return; // duplicate/stale callbacks cannot retarget
                if(this.onFlow)this.flow(error?'callback-error':'callback-success',token.item);
                this.flight=null;
                if(error){this.fail();return;}
                this.pump();
            });
            if(this.onFlow)this.flow('write-observed',item);
            this.record({owner:item.owner,text:item.text,at:item.at,open,bytes,writeInvoked:true});
        }catch(error){
            if(this.flight===token)this.flight=null;
            this.fail();throw error;
        }
        }finally{this.pumping=false;}
    }
    fail() {
        if(this.closed)return;
        this.close();
        // A physical-channel failure concerns the current socket owner, even
        // if the failed flight originated before a same-browser session rejoin.
        this.onError();
    }
    invalidate(owner) {
        if(this.currentOwner()!==owner && this.pending?.owner!==owner)return;
        this.epoch++;
        if(this.pending?.owner===owner)this.pending=null;
        // An issued physical write cannot be cancelled or marked retired here.
        if(this.onFlow)this.flow('invalidate',{owner});
    }
    close() {this.closed=true;this.pending=null;this.epoch++;if(this.onFlow)this.flow('close',null);}
    bounds() {return {physicalInFlight:this.flight?1:0,latestPending:this.pending?1:0,
        inFlightBytes:this.flight?.item.size||0,pendingBytes:this.pending?.size||0};}
}

// These avatar predicates retain the frontend parser's limits and semantics.
function isRecord(value) {
    return !!value && typeof value === 'object' && !Array.isArray(value);
}

function validPosition(value) {
    return isRecord(value) && ['x','y','z'].every(axis => typeof value[axis] === 'number' && Number.isFinite(value[axis]));
}
function validOrientation(value) {
    if (!isRecord(value) || !['x','y','z','w'].every(axis => typeof value[axis] === 'number' && Number.isFinite(value[axis]))) return false;
    const norm = Math.hypot(Number(value.x), Number(value.y), Number(value.z), Number(value.w));
    return norm > 0.99 && norm < 1.01;
}
function validAvatar(value) {
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


export function avatarSnapshotText(value, capture) {
    if(value?.type !== 'avatars')throw Error('Invalid avatar snapshot');
    const text=JSON.stringify(value);
    if(typeof text !== 'string' || text.length > MAX_TEXT_CODE_UNITS || Buffer.byteLength(text) > MAX_TEXT_BYTES)throw Error('Gateway response too large');
    const captured=JSON.parse(text);
    if(!isRecord(captured) || captured.type !== 'avatars' || !Array.isArray(captured.avatars)
        || captured.avatars.length > 10000 || !captured.avatars.every(validAvatar))throw Error('Invalid avatar snapshot');
    if(captured.message !== undefined && typeof captured.message !== 'string')throw Error('Invalid gateway notice');
    if(capture){try{capture(captured);}catch{/* Diagnostics cannot change admission. */}}
    return text;
}
