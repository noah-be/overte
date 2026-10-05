// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact historical V31 CPU sources only; never imported by shipping runners.
import {normalizeStartupIntegrationInput} from './capture-startup-integration-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';
import {constants} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),refuse=()=>{throw Error('Historical movement input source refused');};
const ARCHIVE="4cedbd5237fcc6462c14799a4635d48e886d089c1471c626be943adca97a323e",BEFORE={"browser-client/src/world.ts":"609378a10d67dcd89f3e581b972986425a61ba77720d131eb27ee193c815be3a","browser-client/lab/curate-core-journey.py":"561ebabb5bf707909cab8b819225318adf4b58b01f25c11eba5dfbd3f335b76a","browser-client/tests/integration/capture-software-graphics-source-fixture.mjs":"42b34d78235e576f0146ca7609a936c371315ff8c6aba1b0a7db52b984024a78","browser-client/tests/tablet-capture-software-graphics-manifest.test.mjs":"170c70ed23e618eba3e4d850d5abf1cc98f7f07aa3149504a7457e0dd8952d8e","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"db3ca26884d68fc7761d6bf33ca8187219f534c2b3f8904302dc42232b76ac61","browser-client/tests/integration/real-session.mjs":"5306941171f64f2e385721a017fb90d8f65cc75e887d85f0cd7c21d7a613eb57"},CURRENT={"browser-client/src/world.ts":"5e1dc575628b806ba7683025772439cabd006835c60552826316e333f7039b02","browser-client/lab/curate-core-journey.py":"a9bf4fb8950989c40851ed63e59730467083eeeacd5ff190d25c07497e280363","browser-client/tests/integration/capture-software-graphics-source-fixture.mjs":"e8badee4aaa4eb5dca7a490e4d3b9b0664a83572410e9f99eec943b1d36ac36a","browser-client/tests/tablet-capture-software-graphics-manifest.test.mjs":"1402d355198c5092e2f5fb35cda73551fb4b33123d62683a65233e97faabe791"},HISTORICAL={"browser-client/src/world.ts":["0c3f4a2770cdba7909ca2de030ba8e3bf62fcadfd5faea3c0796005c2ec5edf5","fd86e005c4b24c055da051a0a38385b8f02b25b0945d001bfed9ac577578e4d0"],"browser-client/lab/curate-core-journey.py":["3980961dde13cb9c26b1dbcc0ed2d733cc9aeebe5068347704f6d891e652bc36","915a9d02a812aad92192cf650c3899dd27b1fcb22537f3edf60bd1e2f846da81","d879087afc510171c0e131c69ca40fd5127c77bbe78f6d8f86a4749c3cfb55b4","e6cf19232d627a7daa232cb299e365f4b2154b06bbf36f1946ce72f564ccb3e6"]};
export function decodeCaptureV31History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[n,h]of Object.entries(BEFORE)){const row=value.files[n];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==h||typeof row.source!=='string'||sha(Buffer.from(row.source))!==h)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV31History(){
 if(!history)history=(async()=>{
  const file=fileURLToPath(new URL('../fixtures/capture-v31-movement-input-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();
  const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;
   while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
   const z=await h.stat();if(n!==a.size||n>131072||!['dev','ino','size','mtimeMs','ctimeMs'].every(k=>a[k]===z[k]))refuse();return decodeCaptureV31History(b.subarray(0,n));
  }finally{await h.close();}
 })();return history;
}
export async function readCaptureV31Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV31History()).files[relative].source;}
export async function recoverCaptureV31Input(relative,bytes){
 bytes=normalizeStartupIntegrationInput('movement',relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const h=sha(bytes);if(h===BEFORE[relative]||HISTORICAL[relative]?.includes(h))return bytes;if(h!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV31Source(relative));
}
