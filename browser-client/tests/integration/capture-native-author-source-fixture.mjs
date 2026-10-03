// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v19 CPU fixtures only. Never imported by production.
import {recoverCaptureV20Input} from './capture-embedded-context-type-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical native author source refused');};
const ARCHIVE="89a0fbf8dc642b3fd15bd02a5b371a00299d097d856c01aa22abee88a56ea8a1",BEFORE={"browser-client/tests/fixtures/capture-context-diagnostic-v19-complete-source-manifest.json":"71ec9ab7653018e8ec3c3443887dfb9ba422370b92c5d3da4644d1298672f5c1","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"8eb5df144aa9d7dbf6ee0967cac0812fa41fa62907733b274537241ac8926d0a","browser-client/tests/tablet-capture-context-diagnostic-manifest.test.mjs":"41662d5ea78aa514cc47939f8c77f2f2a1e61015092f8f74eb472741239f91a4","browser-client/gateway/native-avatar-passive-integration.test.mjs":"2835e3f66d15678fec280250f6d1095a9a3d6b729938a18a95c61bc315a0e5a6","browser-client/tests/integration/tablet-ptt-native-peer.mjs":"0612ba9af9f17ede4eb657a0fdfeb3921738d9b17d8b1cd2dcdb1e78fa2da5f7"},CURRENT={"browser-client/tests/tablet-capture-context-diagnostic-manifest.test.mjs":"c6ed3a734ee1ddf51d28de4fb284ee58793700628ac89ddfffd3d6d61419554a"};
export function decodeCaptureV19History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV19History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v19-native-author-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV19History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV19Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV19History()).files[relative].source;}
export async function recoverCaptureV19Input(relative,bytes){
 if(Buffer.isBuffer(bytes)&&Object.hasOwn(BEFORE,relative)&&sha(bytes)===BEFORE[relative])return bytes;
 bytes=await recoverCaptureV20Input(relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV19Source(relative));
}
