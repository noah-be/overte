// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {open,realpath,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const EMOTE_SOURCE_SHA256='968b5af22e88242fcbc8f09eb0a85161baa70a9cfd3dd5af0edec957fa0e5762';
const MAX_SOURCE_BYTES=32*1024;
function once(source,before,after){if(source.split(before).length!==2)throw Error('Unsupported installed Emote source');return source.replace(before,after);}
/** Correct only the verified packaged script; retain its native animation/restore handlers. */
export function buildBrowserEmoteOverride(source){
    if(typeof source!=='string'||Buffer.byteLength(source,'utf8')>MAX_SOURCE_BYTES||createHash('sha256').update(source).digest('hex')!==EMOTE_SOURCE_SHA256)throw Error('Unsupported installed Emote source');
    source=once(source,'        if (ANIMATIONS[emoteName].resource.state === FINISHED) {','        if (ANIMATIONS[emoteName].resource.state === FINISHED) {\n            var frameCount;\n            if (activeEmote !== emoteName) {\n                var selectedAnimation = ANIMATIONS[emoteName].animation;\n                var frames = selectedAnimation && selectedAnimation.frames;\n                frameCount = frames && frames.length;\n                if (typeof frameCount !== "number" || !isFinite(frameCount) || frameCount < 1 || Math.floor(frameCount) !== frameCount || frameCount > 9007199254740991) { return; }\n            }');
    return once(source,'                    var frameCount = ANIMATIONS[emoteName].animation.frames.length;\n','');
}
async function readTrusted(filename){const f=await open(filename,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const info=await f.stat();if(!info.isFile()||info.size>MAX_SOURCE_BYTES)throw Error('Unsupported installed Emote source');const bytes=Buffer.alloc(MAX_SOURCE_BYTES+1);let length=0;while(length<bytes.length){const read=await f.read(bytes,length,bytes.length-length,length);if(!read.bytesRead)break;length+=read.bytesRead;}if(length>MAX_SOURCE_BYTES)throw Error('Unsupported installed Emote source');return bytes.subarray(0,length).toString('utf8');}finally{await f.close();}}
/** Cache validated bytes at gateway startup; no visitor can choose a target or version. */
export async function loadBrowserEmotePackage(defaultScriptsURL){
    const url=new URL(defaultScriptsURL);if(url.protocol!=='file:'||url.host||url.search||url.hash)throw Error('Unsupported installed Emote path');
    const defaults=fileURLToPath(url);if(path.basename(defaults)!=='defaultScripts.js')throw Error('Unsupported installed Emote path');
    const target=path.join(path.dirname(defaults),'system/emote.js');if(await realpath(target)!==target)throw Error('Installed Emote source must be canonical');
    const generated=buildBrowserEmoteOverride(await readTrusted(target));
    return {sourceSHA256:EMOTE_SOURCE_SHA256,async prepare(directory){const source=path.join(directory,'browser-emote.js');await writeFile(source,generated,{flag:'wx',mode:0o600});return {readOnlyOverrides:[{source,target}]};}};
}
