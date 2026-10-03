// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v20 CPU fixtures only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical embedded context type source refused');};
const ARCHIVE="fbcab7588e2fc92899595c1f3ac8d8409b45bcbd2b8a6414c14ca4b9d89541c8",BEFORE={"browser-client/tests/fixtures/capture-native-author-v20-complete-source-manifest.json":"7dc96c6a3398480454c0d8658e96a1efc6104732b0bd10c7d75325456e212ff1","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"e05ac323ff34ba420fdb864f1ccf58a0a73084758b86ed351f902d3788bd25b9","browser-client/tests/tablet-capture-native-author-manifest.test.mjs":"f3c6e4d77b5b958f78fd519082df284d4ce107a3beda2dc7c2bd418e58ffd3be","browser-client/tests/fixtures/embedded-world.ts":"b8e3e6d8d5a27f039f68a85c2aee708cfa34a95824126f714786af61b4c19966","browser-client/tests/integration/capture-embedded-context-source-fixture.mjs":"c55f4c078bfbc04cc0970a3f3ac2458e2b3885710e01685a84b93d2e4a7e8316","browser-client/tests/integration/capture-native-author-source-fixture.mjs":"88882a3c2d8a7877683fab4698ea5ce7ad332fc015ff6d1b26487823bec72aa1"},CURRENT={"browser-client/tests/tablet-capture-native-author-manifest.test.mjs":"3d26389f565ad64459e6bd1c9823aa159206832029df399bf4e269ee8b9a505f","browser-client/tests/fixtures/embedded-world.ts":"7f14c6b4ea8c66db331f4cae71534d84a4be469efb6b0c47904c97344972d5ed","browser-client/tests/integration/capture-embedded-context-source-fixture.mjs":"4278e23ba7b7291971c48e11e3857f44b71f57dc7476565588cf82b9df4488de","browser-client/tests/integration/capture-native-author-source-fixture.mjs":"4fe518c7f63a5e5eb5072e621c2ef20111eecbc04cad3ae5027a88700c902852"};
export function decodeCaptureV20History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV20History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v20-context-type-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV20History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV20Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV20History()).files[relative].source;}
export async function recoverCaptureV20Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV20Source(relative));
}
