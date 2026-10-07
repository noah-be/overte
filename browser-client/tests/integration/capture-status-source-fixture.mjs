// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Whole historical v8 CPU inputs only. Never imported by production or preparation.
import {recoverCaptureV9Input} from './capture-reconnect-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical status source refused');};
const ARCHIVE="b95883e4eda60572830c7bef5130ad72bd72c2f459b7cb08021683bc83a0dc2e",BEFORE={"gateway/browser-capture-overrides.mjs":"38aa8a75aeca858af220f98a020fc6ab806b5611a28c6d3da1ea377b0e6f40bc","tests/fixtures/capture-readback-v8-complete-source-manifest.json":"66c7ce8e7723cfff9ba1c88a0d59730214c896def3fe9597db98d777d790db31","tests/integration/capture-lookahead-source-fixture.mjs":"0f0a99dbd92025346bb6dd40bf8c0e2e0a064f1eddf1ed707d2b05a14ecc4ab8","tests/integration/capture-readback-source-fixture.mjs":"e666b298307a8e5c882ea4fa7cfc193f06df9712b8a66e0969c98484581d1153","tests/integration/capture-source-fixture.mjs":"eb4dc8764b9db77cec674710c67504ff9df3f04e43aadf2bcfd086a8136a4ca1","tests/integration/prepare-tablet-capture-acceptance.mjs":"c39ac23912b90ab0991943f827379e26931099b7df201572f4d7158ee4e589f0","tests/integration/public-hub.mjs":"883c4f95ce01e7ae0ae4b249ad5c55a8a997bff88797b2d09d18035685e26114","tests/integration/tablet-sit-world-stop-session.mjs":"e86aea1e3587d9aa4eece135eb8c5ad6a4f94bfc9d71bb6a96d2f375d3f87e67","tests/tablet-capture-readback-manifest.test.mjs":"48fbea79ac8c823c142f61b8b6b4afa1fb2b00046eef4bfc06bf8976cfec1ac1","gateway/server.mjs":"fa16513f98327619bea099778500b297f2ddcf6d0f897c98fb3a0b9dcacfe2b2"},CURRENT={"gateway/browser-capture-overrides.mjs":"a98031e5365a25318d5a25d0841193f3826ef0f53bac2a1e59d4b1dc86e3b20d","tests/integration/capture-lookahead-source-fixture.mjs":"0780a0352970b0f1ca1ad2170fc8eeb098120a6f2fd2a00657a0b1bf0aa43ba6","tests/integration/capture-readback-source-fixture.mjs":"b8e6a566222b73dac326cfaee6dadaacfff1148a38e236c2c83c430c467ccfbc","tests/integration/capture-source-fixture.mjs":"0df330d2d1fefba1f29d0aded87231890d8091989a2dd7addd8a319f12239c08","tests/integration/public-hub.mjs":"d1a19bd2f65b1b463700c5c9216d68d74692047164e66338bed7d9b4e0a78ea8","tests/integration/tablet-sit-world-stop-session.mjs":"6eb2e9cf74efd98aefb888361c54693ab9234471d92d2751be86702cb9af6442","tests/tablet-capture-readback-manifest.test.mjs":"f9ded879903916c8a8c07c8ba254f1b90782853c0fffdd82118353413cd7b644","gateway/server.mjs":"637c257b80c60bf835468f5a1588471cdc3e4f29c7c3318ae33e2ac746694656"};
export function decodeCaptureV8History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const b=gunzipSync(bytes,{maxOutputLength:524288}),v=JSON.parse(b);
 if(!v||v.version!==1||Object.keys(v).sort().join(',')!=='files,version'||Object.keys(v.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[k,hash]of Object.entries(BEFORE)){const r=v.files[k];if(!r||Object.keys(r).sort().join(',')!=='sha256,source'||r.sha256!==hash||typeof r.source!=='string'||sha(Buffer.from(r.source))!==hash)refuse();Object.freeze(r);}
 Object.freeze(v.files);return Object.freeze(v);
}
let history;
export async function readCaptureV8History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v8-status-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV8History(b.subarray(0,n));}finally{await h.close();}})();
 return history;
}
export async function readCaptureV8Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV8History()).files[relative].source;}
export async function recoverCaptureV8Input(relative,bytes){
 bytes=await recoverCaptureV9Input(relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();
 return Buffer.from(await readCaptureV8Source(relative));
}
