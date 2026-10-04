// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole-c624 V30 CPU history only; never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical startup runtime source refused');};
const ARCHIVE="0639d013e67225cfc90404e3c4d36d11ebc473a8ba95fc5d25e183b60b48f0d5",BEFORE={"browser-client/gateway/server.mjs":"6f22ccc165ab96d61d281f9deefbabb2fc4d249dd68121bfac9c021e5a644c7e","browser-client/gateway/worker-sandbox.mjs":"8a936adad775e1b422fdb50390391336afe640843662d606af675952e780130f","browser-client/gateway/worker-sandbox.test.mjs":"adc7edd32bb7aac6a4d985108884118de1ad3857e12428b626e28faabbb6a333","browser-client/tests/fixtures/capture-avatar-consumption-v30-complete-source-manifest.json":"401f70b0e627d0a672bf73c7acf1c9c7b0916e21707eb39e7268356827a43dcc","browser-client/tests/fixtures/native-ignored-fbx-pixels.ts":"7c6e055d18afbcbde751647b9778768410ebc8543e5d0bdbbc9fe2b09c714e55","browser-client/tests/integration/capture-avatar-consumption-source-fixture.mjs":"9d58b20726f49a62d294d1e248327d242104a40c08bbd60940abbb46b47a9425","browser-client/tests/integration/native-ignored-fbx-pixels.mjs":"c5c1e0a8617d44bb6e7151b759450ddae8b083f0458a7917a9ec0087925a5d2a","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"175a017fbb8707c364ba12c0279cb6e68ef36f9fcefc9becbe1a4a4a4e930dce","browser-client/tests/native-ignored-fbx-diagnostics.test.mjs":"3796ff6c019e6d46886ba9f85c4aecdb5ac4bacaff90a810513861ccb2490f82","browser-client/tests/tablet-capture-avatar-consumption-manifest.test.mjs":"435dcb030c7cf3ea00daa1d01ef04cedc30cfa20afae518cb7f13e56f1667ec3"},CURRENT={"browser-client/gateway/server.mjs":"79dde3d420fb6c21687437930751017e4872a813ced6d1a5e77afffd24cd6576","browser-client/gateway/worker-sandbox.mjs":"e7450d00ea046eba01e792ce5aa1bbe44655943ccaee528dd132e01006b4137a","browser-client/gateway/worker-sandbox.test.mjs":"890336032ab241b16f6b80f2dd5c00bc210f7e35a5abdd69f8696792dc240618","browser-client/tests/fixtures/native-ignored-fbx-pixels.ts":"2584429dfda183804772c567b9623ff3c9433af1db8bad24dbaad52b6963d1b8","browser-client/tests/integration/capture-avatar-consumption-source-fixture.mjs":"8cdb62db4553990e9e7358d0d891051299e5e79d9f6c22d91313c0cc9ecd008c","browser-client/tests/integration/native-ignored-fbx-pixels.mjs":"4d5f56fe9c3870cc9dbcecc8f4140d7edba526cbeb2da57c8d8f32be665f35c4","browser-client/tests/native-ignored-fbx-diagnostics.test.mjs":"76968e586122bb4e2bc7083d94bcc3f36edd8f87330fcc2f858bffc7d7d85381","browser-client/tests/tablet-capture-avatar-consumption-manifest.test.mjs":"30ee2befd7c510cde1bde924213ce6932c7a344d2bd12b35565214b79643b0ef"},EXTERNAL_CURRENT={},HISTORICAL={"browser-client/gateway/server.mjs":["116c45aae6ca9587b546e92bb88b4bd5472ff5100226994b0fced3c80263f45f","637c257b80c60bf835468f5a1588471cdc3e4f29c7c3318ae33e2ac746694656","6d5d81332a41a66df667fa1f8d75a5bbd1c29a345ccbb85fcb75e89419642099","a9697929f62e58274f9753c774b2f5b80c4e32d1f3c87a9909aa21e84ddd9119","e17fae1f721ed162e131309c983041ef824d5688080e5053b6b98f2f9f4722ea","ee69773f46915d97bbf3055657fbf2f00ee7f7136273b62c3a9a2b99ea3b00fc"],"browser-client/gateway/worker-sandbox.mjs":["984fcaf01a09518c5df3032572a357790941e3de3a113c82b1badb218009e5e9"],"browser-client/tests/integration/native-ignored-fbx-pixels.mjs":["7edd8b8938c7d6ac168182e51d1d40ce32c0eb74d937d7092f52f223b0365821"],"browser-client/tests/fixtures/native-ignored-fbx-pixels.ts":["500565d9656c93755b877d12ce706c82d29fb1ba43806da739e4a2edaa59d307"]};
export function decodeCaptureV30History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV30History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v30-startup-runtime-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.uid!==process.getuid()||a.nlink!==1||(a.mode&0o022)||!Number.isSafeInteger(a.size)||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||!['dev','ino','size','uid','mode','nlink','mtimeMs','ctimeMs'].every(k=>a[k]===z[k]))refuse();return decodeCaptureV30History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV30Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV30History()).files[relative].source;}
export async function recoverCaptureV30Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative]||HISTORICAL[relative]?.includes(hash))return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV30Source(relative));
}


export async function readCurrentStartupRuntimeSource(relative,input){
 const expected=Object.hasOwn(CURRENT,relative)?CURRENT[relative]:EXTERNAL_CURRENT[relative];if(!expected)refuse();
 const file=input instanceof URL?fileURLToPath(input):input;if(typeof file!=='string'||await realpath(file)!==file)refuse();
 const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const a=await h.stat();if(!a.isFile()||a.uid!==process.getuid()||a.nlink!==1||(a.mode&0o022)||!Number.isSafeInteger(a.size)||a.size<1||a.size>262144)refuse();
 const b=Buffer.alloc(262145);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
 const z=await h.stat();if(n!==a.size||n>262144||!['dev','ino','size','uid','mode','nlink','mtimeMs','ctimeMs'].every(k=>a[k]===z[k])||sha(b.subarray(0,n))!==expected)refuse();return b.subarray(0,n);
 }finally{await h.close();}
}

export async function prepareStartupV30HistoryReaders(moduleURL,reader){
 const entries=new Map();
 for(const relative of ['browser-client/tests/fixtures/native-ignored-fbx-pixels.ts','browser-client/tests/integration/native-ignored-fbx-pixels.mjs']){
  const file=fileURLToPath(new URL('../'+relative.slice('browser-client/'.length),moduleURL));
  const current=await readCurrentStartupRuntimeSource(relative,file),before=Buffer.from(await readCaptureV30Source(relative));
  entries.set(file,{current,before});
 }
 return {readFileSync(input,options){
  const file=input instanceof URL?fileURLToPath(input):input,entry=entries.get(file);
  if(!entry)return reader(input,options);
  const bytes=reader(input);if(!Buffer.isBuffer(bytes)||!bytes.equals(entry.current))refuse();
  return typeof options==='string'?entry.before.toString(options):Buffer.from(entry.before);
 }};
}
