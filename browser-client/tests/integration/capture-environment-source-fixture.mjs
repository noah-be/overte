// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v10 CPU fixtures only. Never imported by production.
import {recoverCaptureV11Input} from './capture-loading-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
import {recoverCaptureV14Input} from './capture-reviewed-environment-source-fixture.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical environment source refused');};
const ARCHIVE="0803029271616004ed06df64fd8944e78a387fe3c3d16bd17842d9e05e96f2ce",BEFORE={".github/workflows/browser-client.yml":"36c9c308d37c38e1fcf9da2ec6b9a54be9446bb2e5ae439acd414909696a0fcc","browser-client/lab/README.md":"3538e7e9184b585d5ecf4ec9b494d89a68578ac2d27b6b8de4eada5d627b10ce","browser-client/tests/integration/capture-reconnect-source-fixture.mjs":"0dd51aa28b2447513d3a82c259c7f38cdd6df9ac064642b5ea71bdb23e3ba5e4","browser-client/tests/tablet-capture-reconnect-manifest.test.mjs":"10d8956a56ee9437ecf1bcfd2368fa1c4788719ac62a93a21ddfa8b772afd1ad","browser-client/tests/tablet-capture-reacquisition-manifest.test.mjs":"be273205c43c1be072fe6a04e57a4ef0de2e083f64cffdb955633985411d4c8c","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"d04b297ab5051de714bca86556c66a2fc0527da1612027127894f08300c34ae7","browser-client/tests/fixtures/capture-reconnect-v10-complete-source-manifest.json":"fc6e6b881054ebb5f010e885ad43a2a05490ae03a06d411e3f9a9c82c8bcc602"},CURRENT={".github/workflows/browser-client.yml":"c832cc8da969af0acdf02d4c71e98d2b6ae2d58f5ce3d8496a26fda49b3507c5","browser-client/lab/README.md":"86e5620f014c69879722a90609fb1808a7e55f5592a51fb9ec6d5c7b1070a4cb","browser-client/tests/integration/capture-reconnect-source-fixture.mjs":"1381228ab834c78fa3c7355f203a6d17b68115f6ba7b59ce8e6ec27929baf65b","browser-client/tests/tablet-capture-reconnect-manifest.test.mjs":"e2fa60cd67e5f61d0367fc20834dcf210071954d0ed887b04a236dff8e7c658c","browser-client/tests/tablet-capture-reacquisition-manifest.test.mjs":"90f1938bf363abfea3c6e428dfbd095e031651d7c61ad8cf02c9909c30185f33"};
export function decodeCaptureV10History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV10History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v10-environment-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV10History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV10Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV10History()).files[relative].source;}
export async function recoverCaptureV10Input(relative,bytes){
 if(Buffer.isBuffer(bytes)&&Object.hasOwn(BEFORE,relative)&&sha(bytes)===BEFORE[relative])return bytes;
 bytes=await recoverCaptureV14Input(relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();bytes=await recoverCaptureV11Input(relative,bytes);if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV10Source(relative));
}
