// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v16 CPU fixtures only. Never imported by production.
import {recoverCaptureV17Input} from './capture-embedded-diagnostic-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical avatar diagnostic source refused');};
const ARCHIVE="f74ea6ab21bdd9b43b72d36be7becff8f81ab43a89bcb55784fc5e8be1072d59",BEFORE={"browser-client/tests/fixtures/capture-chrome-readme-v16-complete-source-manifest.json":"2015b1a74bbc53ad5b1c51f91cd25b59a6f0dafbd3f5da8bc265d002851e25e9","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"858c4dd12e75adf875a39b8a686dc25cc2d8a7b4197d90d24e614ed68ca5f8d3","browser-client/tests/integration/capture-chrome-readme-source-fixture.mjs":"dd20aec8b39210d7c64e39cc93507cc99d98b198ad358c8c2014306e6969a1a8","browser-client/tests/tablet-capture-chrome-readme-manifest.test.mjs":"e9a2d65abd81eab9ad7802c8380aa868f4cf44ab286e8f3cfa6ebf26a7892704",".github/workflows/browser-client.yml":"1c35849c3a5dd71bccc7bd90125c12d5df7a1cb805e474be9174f87309cdd8ef"},CURRENT={"browser-client/tests/integration/capture-chrome-readme-source-fixture.mjs":"0d24f497d51ede1c324eb2db62e0fa3d4b526ebc14e427fadef4863dbd5201a1","browser-client/tests/tablet-capture-chrome-readme-manifest.test.mjs":"9fb1d32eee28f783e2c913ab6564b31113d4a539f7d558b55ab9c31c898add62",".github/workflows/browser-client.yml":"a816f629c06196be7de077eb1a62fa883f2680d24770a8f6bf934478f28ca813"};
export function decodeCaptureV16History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV16History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v16-avatar-diagnostic-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV16History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV16Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV16History()).files[relative].source;}
export async function recoverCaptureV16Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();bytes=await recoverCaptureV17Input(relative,bytes);if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative]||(relative===".github/workflows/browser-client.yml"&&hash==="c832cc8da969af0acdf02d4c71e98d2b6ae2d58f5ce3d8496a26fda49b3507c5"))return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV16Source(relative));
}
