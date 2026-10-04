// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole39ff V28 historical CPU inputs only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical pruning and flight source refused');};
const ARCHIVE="0730ae2d8908ad8d4b074d65fcc489309a24bb3dca1890ede85ab188d6306270",BEFORE={"browser-client/tests/fixtures/capture-avatar-flow-v28-complete-source-manifest.json":"fea03ac81a676cb02128b6ab13ec5047be98007b09429e369418b4cf47ad3aca","browser-client/tests/integration/capture-avatar-flow-source-fixture.mjs":"4f2d66c2ba0b71b090a88e9e44a3427d45ca6c85ace9f325e6132fa31bec87fc","browser-client/tests/tablet-capture-avatar-flow-manifest.test.mjs":"fb051eeef350fd250c29f89c9ca7bd6b4db406aa923416c2b67f61c5023a75e1","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"5bb4c29f0b84fc01852fdb4030bb46d24d499f598f4a557529debc31f5cb4a19","browser-client/gateway/server.mjs":"a9697929f62e58274f9753c774b2f5b80c4e32d1f3c87a9909aa21e84ddd9119","browser-client/gateway/native-avatar-stdout-projection.mjs":"f8ea6848bda41398b9e3d13b8139e872370cbaecb75a163f2c6a3dab6b3fff40","browser-client/tests/integration/native-ignored-fbx-pixels.mjs":"7edd8b8938c7d6ac168182e51d1d40ce32c0eb74d937d7092f52f223b0365821","browser-client/tests/fixtures/native-ignored-fbx-pixels.ts":"500565d9656c93755b877d12ce706c82d29fb1ba43806da739e4a2edaa59d307","browser-client/gateway/avatar-flow.test.mjs":"3e924b19c559ef8d1d23372b00cbff6bd6c51961c078c9b1dfd2b61342a39588","browser-client/tools/curate-avatar-samples.mjs":"e44d28ab00f51b7d16950cab0d6e5dbd08c2e6f32c473918db555d9868144c10","browser-client/tests/integration/capture-software-managed-source-fixture.mjs":"200a426f6c76a6cd379ee7505906753c8dd7a0d67fc255fda67a3b77821809f2","browser-client/tests/tablet-capture-software-managed-manifest.test.mjs":"6e9143b348733d407fd2b34bbdb0f632f4d74de55489d3a2e4c0b49311f10b02","browser-client/tests/native-avatar-curation.test.mjs":"14b9029c936f6248b7f1e8e84e96b62b4bab35a3f9ac9b92aa5485740217fc22","browser-client/tests/avatar-delivery-source-fixture.test.mjs":"f140826bffbb18ed51aa31e34deb3437425c57b16b865edd37e6a488f26bdd0f"},CURRENT={"browser-client/tests/integration/capture-avatar-flow-source-fixture.mjs":"518616598b8f6001ecfe1d6169589de2644ac3c66ca2035c6cf3162357348b79","browser-client/tests/tablet-capture-avatar-flow-manifest.test.mjs":"1ec7f49c056793c90fbd3d79a4d21a8af95d48fb5b6cd532df11376086cb7469","browser-client/gateway/server.mjs":"ee69773f46915d97bbf3055657fbf2f00ee7f7136273b62c3a9a2b99ea3b00fc","browser-client/gateway/native-avatar-stdout-projection.mjs":"b705c89fadda9d978c1323c5b264196cab2a1f3e70d3f9fea182f991d2bd702c","browser-client/tests/integration/native-ignored-fbx-pixels.mjs":"c5c1e0a8617d44bb6e7151b759450ddae8b083f0458a7917a9ec0087925a5d2a","browser-client/tests/fixtures/native-ignored-fbx-pixels.ts":"7c6e055d18afbcbde751647b9778768410ebc8543e5d0bdbbc9fe2b09c714e55","browser-client/gateway/avatar-flow.test.mjs":"0f83bbeb6d1e95227d7279a8160ee8caf3142ab446fe2026f76f790f5d12053c"},EXTERNAL_CURRENT={},HISTORICAL={"browser-client/gateway/server.mjs":["116c45aae6ca9587b546e92bb88b4bd5472ff5100226994b0fced3c80263f45f","637c257b80c60bf835468f5a1588471cdc3e4f29c7c3318ae33e2ac746694656","6d5d81332a41a66df667fa1f8d75a5bbd1c29a345ccbb85fcb75e89419642099","e17fae1f721ed162e131309c983041ef824d5688080e5053b6b98f2f9f4722ea"],"browser-client/gateway/native-avatar-stdout-projection.mjs":["90c7c18ab0c35e85620bcfa94427253232715da53c0abaf781e817b14515ea3f","a6ff49b5214da56f4713ceadd68e9048c45bb2680e45b81538bfe624a39ec0f7","e2d1a517165c17543cbc03df8bf1241861e974a690b32fba74ecfabe1edc309e","eb6a09fd81cf973077f40fcd0d108884c78aea60540782799acd0aca6c46b860"]};
export function decodeCaptureV28History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV28History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v28-pruning-flight-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV28History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV28Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV28History()).files[relative].source;}
export async function recoverCaptureV28Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative]||HISTORICAL[relative]?.includes(hash))return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV28Source(relative));
}


export async function readCurrentPruningFlightSource(relative,input){
 const expected=Object.hasOwn(CURRENT,relative)?CURRENT[relative]:EXTERNAL_CURRENT[relative];if(!expected)refuse();
 const file=input instanceof URL?fileURLToPath(input):input;if(typeof file!=='string'||await realpath(file)!==file)refuse();
 const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const a=await h.stat();if(!a.isFile()||a.uid!==process.getuid()||a.nlink!==1||(a.mode&0o022)||!Number.isSafeInteger(a.size)||a.size<1||a.size>262144)refuse();
 const b=Buffer.alloc(262145);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
 const z=await h.stat();if(n!==a.size||n>262144||!['dev','ino','size','uid','mode','nlink','mtimeMs','ctimeMs'].every(k=>a[k]===z[k])||sha(b.subarray(0,n))!==expected)refuse();return b.subarray(0,n);
 }finally{await h.close();}
}



export async function prepareAvatarV28FlowHistoryReaders(originalReadFileSync){
 const server='browser-client/gateway/server.mjs',projector='browser-client/gateway/native-avatar-stdout-projection.mjs',collector='browser-client/tools/curate-avatar-samples.mjs';
 for(const relative of [server,projector])await readCurrentPruningFlightSource(relative,new URL('../../'+relative.replace(/^browser-client\//,''),import.meta.url));
 const collectorURL=new URL('../../tools/curate-avatar-samples.mjs',import.meta.url),collectorBytes=originalReadFileSync(collectorURL);if(sha(collectorBytes)!==BEFORE[collector])refuse();
 const oldServer=Buffer.from(await readCaptureV28Source(server)),oldProjector=await readCaptureV28Source(projector),oldCollector=await readCaptureV28Source(collector);
 if(/^import\s/m.test(oldProjector))refuse();
 const projectorURL='data:text/javascript;base64,'+Buffer.from(oldProjector).toString('base64'),projection=await import(projectorURL);
 const anchor="from '../gateway/native-avatar-stdout-projection.mjs'";if(oldCollector.split(anchor).length!==2)refuse();
 const redirected=oldCollector.replace(anchor,'from '+JSON.stringify(projectorURL)),collection=await import('data:text/javascript;base64,'+Buffer.from(redirected).toString('base64'));
 const url=new URL('../../gateway/server.mjs',import.meta.url);
 return Object.freeze({readFileSync:(input,encoding)=>input instanceof URL&&input.href===url.href?(encoding===undefined?Buffer.from(oldServer):encoding==='utf8'?oldServer.toString('utf8'):refuse()):originalReadFileSync(input,encoding),attachNativeAvatarProjection:projection.attachNativeAvatarProjection,projectAvatarTail:collection.projectAvatarTail,collectAvatarSamples:collection.collectAvatarSamples,writeAvatarSamples:collection.writeAvatarSamples});
}
