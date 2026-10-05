// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole24a V29 CPU history only. Never imported by production.
import {recoverCaptureV30Input} from './capture-software-graphics-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical avatar consumption source refused');};
const ARCHIVE="b7a38835df542d72902b6de93f74ae5b05ed23d54c074e6fdd37cbfac121c802",BEFORE={"browser-client/gateway/avatar-snapshot-sender.mjs":"f42328972ccaff3a52736771f377380bc96c81c388353842c7fe386052cc188d","browser-client/gateway/server.mjs":"ee69773f46915d97bbf3055657fbf2f00ee7f7136273b62c3a9a2b99ea3b00fc","browser-client/src/compressed-color-session.ts":"e18af74fe59593bf9f1aee0ce7a91f0e6910ed5e903868f646f1311d61c42fcf","browser-client/src/main.ts":"3b0bcf6ef6e607e7b4035bd6dd11bbf686f3cf01370d1715622c03bf5f8c3d8b","browser-client/src/session.ts":"79d78c5c170917c79c5d740456a419a5656528ea7a961ab1ef2b3dc92e2779c1","browser-client/tests/fixtures/capture-pruning-flight-v29-complete-source-manifest.json":"0e3ac94a9d3e4b8271c356b5752c38439f183a146561b6bfde2c256efcbfb489","browser-client/tests/integration/capture-pruning-flight-source-fixture.mjs":"677a649aa392d23eacfc48c2ee94b24a1e2c831a823639e6e833ff9702c5bb0b","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"a680c2475870639967f0a71b11a6cdba5b5784d6858f089060664c84b24e61d5","browser-client/tests/tablet-capture-pruning-flight-manifest.test.mjs":"e66cb8d675663f780c223184e536f153f0bb4edc931e2e03f7d3a70e683067d1"},CURRENT={"browser-client/gateway/avatar-snapshot-sender.mjs":"a8f2e55c57ed68922aa490a6ec859c1683873d11707303679cf92ccbc67804a5","browser-client/gateway/server.mjs":"6f22ccc165ab96d61d281f9deefbabb2fc4d249dd68121bfac9c021e5a644c7e","browser-client/src/compressed-color-session.ts":"5611f1651f34b05b35901fcbb421c8b7552ba94c81e2ba407740136473e264cc","browser-client/src/main.ts":"ee249e728c454206ec31e744c8944efa769c8d651f8c87a4e27a5f7a73393fb7","browser-client/src/session.ts":"f7f586ef04c496a4900b9fab7991f27661eb18afeaa333dc9460237ba55e0ea1","browser-client/tests/integration/capture-pruning-flight-source-fixture.mjs":"ed6d2f882f2e7e88ed7e03d2953cc9e454c0c2513514ce667fc04a6bff2fc5b9","browser-client/tests/tablet-capture-pruning-flight-manifest.test.mjs":"da358a288fb373135b59811e3467e28f8bfc2992be1e5476cb0deed9ac726d3b"},EXTERNAL_CURRENT={},HISTORICAL={"browser-client/gateway/server.mjs":["116c45aae6ca9587b546e92bb88b4bd5472ff5100226994b0fced3c80263f45f","637c257b80c60bf835468f5a1588471cdc3e4f29c7c3318ae33e2ac746694656","6d5d81332a41a66df667fa1f8d75a5bbd1c29a345ccbb85fcb75e89419642099","a9697929f62e58274f9753c774b2f5b80c4e32d1f3c87a9909aa21e84ddd9119","e17fae1f721ed162e131309c983041ef824d5688080e5053b6b98f2f9f4722ea"],"browser-client/gateway/avatar-snapshot-sender.mjs":["026274463190fe6f2d25d6e900713cee55e4520f9d3595dccabd35eab361699f"],"browser-client/src/main.ts":["8059c8e774e9f641d85f0255dcd6e37f0143cf005a7dcb5a4d7d714eedca4ac4"]};
export function decodeCaptureV29History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV29History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v29-avatar-consumption-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV29History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV29Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV29History()).files[relative].source;}
export async function recoverCaptureV29Input(relative,bytes){
 bytes=await recoverCaptureV30Input(relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative]||HISTORICAL[relative]?.includes(hash))return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV29Source(relative));
}


export async function readCurrentAvatarConsumptionSource(relative,input){
 const expected=Object.hasOwn(CURRENT,relative)?CURRENT[relative]:EXTERNAL_CURRENT[relative];if(!expected)refuse();
 const file=input instanceof URL?fileURLToPath(input):input;if(typeof file!=='string'||await realpath(file)!==file)refuse();
 const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const a=await h.stat();if(!a.isFile()||a.uid!==process.getuid()||a.nlink!==1||(a.mode&0o022)||!Number.isSafeInteger(a.size)||a.size<1||a.size>262144)refuse();
 const b=Buffer.alloc(262145);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
 const z=await h.stat();if(n!==a.size||n>262144||!['dev','ino','size','uid','mode','nlink','mtimeMs','ctimeMs'].every(k=>a[k]===z[k]))refuse();const recovered=await recoverCaptureV30Input(relative,b.subarray(0,n));if(sha(recovered)!==expected)refuse();return recovered;
 }finally{await h.close();}
}
