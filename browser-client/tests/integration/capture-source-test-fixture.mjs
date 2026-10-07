// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v12 CPU fixtures only. Never imported by production.
import {recoverCaptureV13Input} from './capture-image-transport-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical source-test fixture refused');};
const ARCHIVE="1cfa6581608fc10843cdf325de24cde5056f7a8ac89a3c9b5ed9521daeaafeaa",BEFORE={"browser-client/tests/chrome-journey-defaults.test.mjs":"757f3669fa00a8581220ab05c5f7fa008ad8ecde7db47af23699e54ea211877d","browser-client/tests/hub-entity-membership-output.test.mjs":"7a510292b956f6824158ce9f2ab30efe30f1f2c319b374965754a9ec4fad99b6","browser-client/tests/integration/capture-loading-source-fixture.mjs":"2918caea0737fe6b4e987f3cf4a85fd29256c5b0b59ad5f0adb996356c1c5726","browser-client/tests/tablet-capture-loading-manifest.test.mjs":"7fc8b5c1c8a4560b92f7e6fa106d83a299beb452304524a8285efd44c3fb90b6","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"4bd044a42360ad912ce932f8cf3f07ce146d9a4a08d5840db3eb9a1e60f3a9cb","browser-client/tests/fixtures/capture-loading-v12-complete-source-manifest.json":"f67b57ecc9294410fe8dc73ae56b704d1481e8a3ad4c63fb3ce1ada2f6134b37"},CURRENT={"browser-client/tests/chrome-journey-defaults.test.mjs":"03a94c9e2a10bb3f9c7d60c898289578a823162bde62a1be95a8825c863a4365","browser-client/tests/hub-entity-membership-output.test.mjs":"b6f5a4069b5ab5066dde85d79665c2e1a2c7a190165a104d257be04af7d22764","browser-client/tests/integration/capture-loading-source-fixture.mjs":"6ef5132fdf4e9d1d2a6cfd53f7ffda83a2baf2b1cbd7c43865b5e73e8f933707","browser-client/tests/tablet-capture-loading-manifest.test.mjs":"41ad94b1eddb2e2feb134e6147b125b4e535e2cb2bfe83465df37671322fa6b8"};
export function decodeCaptureV12History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV12History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v12-source-test-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV12History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV12Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV12History()).files[relative].source;}
export async function recoverCaptureV12Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(Object.hasOwn(BEFORE,relative)&&sha(bytes)===BEFORE[relative])return bytes;bytes=await recoverCaptureV13Input(relative,bytes);if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV12Source(relative));
}
