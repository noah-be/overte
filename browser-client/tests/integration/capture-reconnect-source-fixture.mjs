// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v9 CPU fixtures only. Never imported by production.
import {recoverCaptureV10Input} from './capture-environment-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical reconnect source refused');};
const ARCHIVE="51cb27baa3ef0362a741f3189ba069e000dc623f09afedc32f4f1406753ef11f",BEFORE={"src/tablet.ts":"6bff82a459b0b2b3a2c6f0c8abc0ba120dc89976a5215ff2c537f7c5c63a28b4","src/world.ts":"a732522ba5e3d9b710d7402e9fa564c7da856d90147a2fa7c2edbb9b14a1c41c","src/prepared-fbx-cache.ts":"0b7891b4fd29c4f211751b2ae9fa00a48e086a2037ac382d6e4e4a15750c71fd","tests/integration/capture-status-source-fixture.mjs":"c299c08ebe3e874b4d0653e58f052d79acac632884ea76462ae6f2d7d27d2d68","tests/tablet-capture-status-manifest.test.mjs":"c20a9d35da9d410a7152fdd7906a3917821c3a6b8c1d71ad802e66aeccb6c046","tests/integration/prepare-tablet-capture-acceptance.mjs":"00c666b3ed34f9539ede609a6e35a03864e9f7542b0c8e0112cd5919a771ca42","tests/fixtures/capture-status-v9-complete-source-manifest.json":"e78d679622ce9d3494cadab32288b5c52925267fb3c0f62ffc380e6771220802"},CURRENT={"src/tablet.ts":"cde17fc6d479bf58b287db36e1f56c5f7628fe8699755bfacd9d49411f7096af","src/world.ts":"0c3f4a2770cdba7909ca2de030ba8e3bf62fcadfd5faea3c0796005c2ec5edf5","src/prepared-fbx-cache.ts":"49d6cf20f560eb7b2f795c6f5667cb1a9d37220996f5c8ad80d73c82e426b75b","tests/integration/capture-status-source-fixture.mjs":"6dbf261f8cf55837da2d07e9bb464959a4c0eeacd5f0ea2d460349cc6f8784e3","tests/tablet-capture-status-manifest.test.mjs":"dcf19ded1d8928c8008452f7be973f544c4e7ad41364931a1e66c4f1af54ed84"};
export function decodeCaptureV9History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV9History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v9-reconnect-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV9History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV9Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV9History()).files[relative].source;}
export async function recoverCaptureV9Input(relative,bytes){
 bytes=await recoverCaptureV10Input('browser-client/'+relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV9Source(relative));
}
