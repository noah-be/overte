// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v17 CPU fixtures only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical embedded diagnostic source refused');};
const ARCHIVE="94e6a1e0bbeaa6f5bbf5de55e05aa043f226f63491ef88362d29d05ef39139e3",BEFORE={"browser-client/tests/fixtures/capture-avatar-diagnostic-v17-complete-source-manifest.json":"a4b106047cc97db0219324e0c645b162ed145520cd7c00cb0efdf7eeb8c255d7","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"d11873fa00e5d54eb6b87b803f401274d860b60544b4522b8037881003ffd9b1","browser-client/tests/integration/capture-avatar-diagnostic-source-fixture.mjs":"7e5ece458764b5e70114ee2484ff4935cef7ea7c7d523c2c02b243d7ab5451f9","browser-client/tests/tablet-capture-avatar-diagnostic-manifest.test.mjs":"3266a324bc922146e8eecffcf964690ce16e8fcfdb8a74282fbaccee9f9d17b8","browser-client/tests/integration/embedded-world.mjs":"e02885bc1c7be64d26f24f49784d70bea937948005657bd14baab83260a4511e","browser-client/tests/fixtures/embedded-world.ts":"9020a650627d452dc3662ea2827eab0803623a761a2294b095c1872d1d80617e"},CURRENT={"browser-client/tests/integration/capture-avatar-diagnostic-source-fixture.mjs":"c3221a8584e8e805c85ca8922f9056ae467387f7ebb99a49ff5f3f8ae00abc25","browser-client/tests/tablet-capture-avatar-diagnostic-manifest.test.mjs":"df98d4d58f97143488e17ee0fe1fec49931b7d089c41f49b1d4449e285d69abe","browser-client/tests/integration/embedded-world.mjs":"0963fb2d8d5eec98e47000c1a50402483d392c71953a9799a2f96e8b6e03ff52","browser-client/tests/fixtures/embedded-world.ts":"42a5df3dc25191a04a79da33a488dd8afd249893d5c17dd77ca0f0655a2088df"};
export function decodeCaptureV17History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV17History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v17-embedded-diagnostic-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV17History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV17Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV17History()).files[relative].source;}
export async function recoverCaptureV17Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV17Source(relative));
}
