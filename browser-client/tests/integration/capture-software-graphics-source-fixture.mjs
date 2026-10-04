// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact historical V30 CPU sources only; never imported by shipping runners.
import {open,realpath} from 'node:fs/promises';
import {constants} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),refuse=()=>{throw Error('Historical software graphics source refused');};
const ARCHIVE="d90537fa66150dd8cb24829c255e43b07445fc9b637a18c7646c57d1f2d876b0",BEFORE={"browser-client/tests/chrome-only-defaults.test.mjs":"b5208047eb69d8e9c2113bff444f2880522beb2acb7ca075a5077052784c8c76","browser-client/tests/integration/real-session.mjs":"ec4ac0fb187acbcd650c10295c5c5364a00687c3abab1e24f395934d3a3460a7","browser-client/tests/integration/native-ignored-fbx-pixels.mjs":"c5c1e0a8617d44bb6e7151b759450ddae8b083f0458a7917a9ec0087925a5d2a","browser-client/lab/curate-core-journey.py":"915a9d02a812aad92192cf650c3899dd27b1fcb22537f3edf60bd1e2f846da81","browser-client/tests/integration/capture-avatar-consumption-source-fixture.mjs":"9d58b20726f49a62d294d1e248327d242104a40c08bbd60940abbb46b47a9425","browser-client/tests/tablet-capture-avatar-consumption-manifest.test.mjs":"435dcb030c7cf3ea00daa1d01ef04cedc30cfa20afae518cb7f13e56f1667ec3","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"175a017fbb8707c364ba12c0279cb6e68ef36f9fcefc9becbe1a4a4a4e930dce"},CURRENT={"browser-client/tests/chrome-only-defaults.test.mjs":"d464d0151587dbc81a2e5ad0bad241cfcf08d812f1ed50e7fe53c13b3c9f0bdf","browser-client/tests/integration/real-session.mjs":"5306941171f64f2e385721a017fb90d8f65cc75e887d85f0cd7c21d7a613eb57","browser-client/tests/integration/native-ignored-fbx-pixels.mjs":"a0ca0d4c3e77cf8e5c3007386146ddd3c11a8470c97c4f394b86684f15d55686","browser-client/lab/curate-core-journey.py":"561ebabb5bf707909cab8b819225318adf4b58b01f25c11eba5dfbd3f335b76a","browser-client/tests/integration/capture-avatar-consumption-source-fixture.mjs":"cccb2539ac982466080fe78d2913b9317452d33726f834892186c82395b4885e","browser-client/tests/tablet-capture-avatar-consumption-manifest.test.mjs":"139df1985ecb29f58a96603424c629698a6322199a91a49dfb2fc5bfb966e99a"},HISTORICAL={"browser-client/tests/integration/real-session.mjs":["ca8f8f6502e569c130625ca72403b0a1bf145ac227645a16af88bb43aa7f94a7","daba35297a9090a29a916ddd7658c11b2713fcf1f25d78894e17d9ac922e915b"],"browser-client/tests/integration/native-ignored-fbx-pixels.mjs":["7edd8b8938c7d6ac168182e51d1d40ce32c0eb74d937d7092f52f223b0365821"],"browser-client/lab/curate-core-journey.py":["3980961dde13cb9c26b1dbcc0ed2d733cc9aeebe5068347704f6d891e652bc36","d879087afc510171c0e131c69ca40fd5127c77bbe78f6d8f86a4749c3cfb55b4","e6cf19232d627a7daa232cb299e365f4b2154b06bbf36f1946ce72f564ccb3e6"]};
export function decodeCaptureV30History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[n,h]of Object.entries(BEFORE)){const row=value.files[n];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==h||typeof row.source!=='string'||sha(Buffer.from(row.source))!==h)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV30History(){
 if(!history)history=(async()=>{
  const file=fileURLToPath(new URL('../fixtures/capture-v30-software-graphics-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();
  const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;
   while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
   const z=await h.stat();if(n!==a.size||n>131072||!['dev','ino','size','mtimeMs','ctimeMs'].every(k=>a[k]===z[k]))refuse();return decodeCaptureV30History(b.subarray(0,n));
  }finally{await h.close();}
 })();return history;
}
export async function readCaptureV30Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV30History()).files[relative].source;}
export async function recoverCaptureV30Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const h=sha(bytes);if(h===BEFORE[relative]||HISTORICAL[relative]?.includes(h))return bytes;if(h!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV30Source(relative));
}
