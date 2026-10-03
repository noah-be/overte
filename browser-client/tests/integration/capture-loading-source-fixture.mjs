// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v11 CPU fixtures only. Never imported by production.
import {recoverCaptureV12Input} from './capture-source-test-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical loading source refused');};
const ARCHIVE="b335d454c9a6eb04a71051563d07c390f2bf46dc747409ee21a752b96917e15c",BEFORE={"browser-client/src/world.ts":"0c3f4a2770cdba7909ca2de030ba8e3bf62fcadfd5faea3c0796005c2ec5edf5","browser-client/src/world-image-cache.ts":"ba45a6125087f8b275c939a5e9e36dadac6879a37cb0fbe50d8c19dd9f1c6af9","browser-client/tests/integration/capture-environment-source-fixture.mjs":"90a0cfb3be585afda4d5aad4c563a603de3b4adc2fee1335aadca2830cf7fcfb","browser-client/tests/tablet-capture-environment-manifest.test.mjs":"198f2d6d6b50bb770f54279f5111df84a4b4e76ca3aa148d9c4326a205090032","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"263473ce6423b160a07266b9afff1baae08dab9a4a2242cb3cf2e81fea40874f","browser-client/tests/fixtures/capture-environment-v11-complete-source-manifest.json":"19aa0b6eb4d57ebcdba875b03d9cfebb17d4e17e5c34b4e22efbe3071b5bdf1c"},CURRENT={"browser-client/src/world.ts":"fd86e005c4b24c055da051a0a38385b8f02b25b0945d001bfed9ac577578e4d0","browser-client/src/world-image-cache.ts":"5e3098922fde0a021a605596917062210168f210485783709f24ccc7ea89788b","browser-client/tests/integration/capture-environment-source-fixture.mjs":"2cdc6bcb9d0adb4a32f30a469c6e9b6c3bd49c621bbaa5cc55d7871e543a0e3a","browser-client/tests/tablet-capture-environment-manifest.test.mjs":"4788a4a2e9212d1c14190af72bc3b91bf7194448520f76370d0dcb7ff4d544a5"};
export function decodeCaptureV11History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV11History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v11-loading-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV11History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV11Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV11History()).files[relative].source;}
export async function recoverCaptureV11Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(Object.hasOwn(BEFORE,relative)&&sha(bytes)===BEFORE[relative])return bytes;bytes=await recoverCaptureV12Input(relative,bytes);if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV11Source(relative));
}
