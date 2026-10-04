// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v22 CPU fixtures only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical live context source refused');};
const ARCHIVE="3ee0af6622145e16f0d91f550b1a45652b092ba58fc6afd5043efa5521ed6196",BEFORE={"browser-client/tests/fixtures/capture-context-lifecycle-v22-complete-source-manifest.json":"07fb3dad9cddc8d9cd7b70326756488910ec03d8b83d32ea2a625dbc6611b51f","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"ae0785433377baf51b67c305a76629e6ca8509759718a8dfa69737708d2d8060","browser-client/tests/tablet-capture-context-lifecycle-manifest.test.mjs":"573f8a1da89d90805eb25647ff9f9018f9c7fcdb171d2c12ab097c4293adc7e8","browser-client/tests/integration/capture-context-lifecycle-source-fixture.mjs":"8bae7a46fc59ce939ce452265ae246dab21090131b746c4157a51a81931b31f0","browser-client/src/world-cpu-segments.test.ts":"3c73e289e302c2ded7205130d623b4ca6e093e4f30267fd7824bd30680b1cdba","browser-client/tests/world-native-image-effects.test.ts":"01b13bfbe21f502b0c4a78aeef673357529f05906f47a96317aa1e82b5af6e9f","browser-client/tests/world-owned-escape.test.mjs":"2c46f221a9617507357fbc37f580f5a8e780c778a6c62a1f50525443c7427919"},CURRENT={"browser-client/tests/tablet-capture-context-lifecycle-manifest.test.mjs":"72e3e06dc2d4741dbf2ab75aa825baa831c41ba5673ac59e0f9af6b877aeceed","browser-client/tests/integration/capture-context-lifecycle-source-fixture.mjs":"c93067a9bd213fee170d49f463cdad09fdb8d4aadf56406728ecb06aea424a98","browser-client/src/world-cpu-segments.test.ts":"7fd8a75cf18f2c9c961f1339bcf49e74c72f58e599c2e6f6a7bfd02e5be87c02","browser-client/tests/world-native-image-effects.test.ts":"da9b8513a9562ab2f63b9c60013725369e18b6d5c7111d430055ee90887ee8e6","browser-client/tests/world-owned-escape.test.mjs":"c72a08649e5cf4196d23e7b23220dd94beb26c24535a7aede06e2717fc8f8085"};
export function decodeCaptureV22History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV22History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v22-live-context-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV22History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV22Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV22History()).files[relative].source;}
export async function recoverCaptureV22Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV22Source(relative));
}
