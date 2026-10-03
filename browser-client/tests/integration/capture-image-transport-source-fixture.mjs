// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v13 CPU fixtures only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical image transport source refused');};
const ARCHIVE="34339e38bc8b7013c6fef4169f4e88bfe4f89666be4410f8dd160f86bc288d93",BEFORE={"browser-client/src/world-image-cache.ts":"5e3098922fde0a021a605596917062210168f210485783709f24ccc7ea89788b","browser-client/gateway/server.mjs":"637c257b80c60bf835468f5a1588471cdc3e4f29c7c3318ae33e2ac746694656","browser-client/tests/integration/capture-source-test-fixture.mjs":"33d2272bbe6996195694a7f875ade898a10a04771b3395cd4920414fd4c62984","browser-client/tests/tablet-capture-source-test-manifest.test.mjs":"da8f2b4b45cfd6e3218cce11b0ad0f44c94ff4bf7c71d9a21d5634567557c9bf","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"50c0212f5f585f1534080f21cb47c6c49b7595fbbfd862f6e7d4e38fb4147db6","browser-client/tests/fixtures/capture-source-test-v13-complete-source-manifest.json":"24856ccccaafedd8e15b66c95b3eb97a60424aa0c206eb6e51bec04feb282ae7","browser-client/tests/integration/capture-loading-source-fixture.mjs":"6ef5132fdf4e9d1d2a6cfd53f7ffda83a2baf2b1cbd7c43865b5e73e8f933707","browser-client/tests/tablet-capture-status-manifest.test.mjs":"dcf19ded1d8928c8008452f7be973f544c4e7ad41364931a1e66c4f1af54ed84"},CURRENT={"browser-client/src/world-image-cache.ts":"ff3393a7d243dbdd17b6527071e09f4b812ba16f5f4b9138b2b204664bd41578","browser-client/gateway/server.mjs":"e17fae1f721ed162e131309c983041ef824d5688080e5053b6b98f2f9f4722ea","browser-client/tests/integration/capture-source-test-fixture.mjs":"90038225ad338aaed22f574a2e67bb949d6d97d07d911e0dcab370931b909beb","browser-client/tests/tablet-capture-source-test-manifest.test.mjs":"387e0bca92eec205cb4f3393cbac71991c58e3ef66e3c2119ea78ff36a9e3db9","browser-client/tests/integration/capture-loading-source-fixture.mjs":"226f8cfbf645a95e3e9e279854ca3c868192f139f4262dd863f09d0db758088c","browser-client/tests/tablet-capture-status-manifest.test.mjs":"4250047ca66ae2cd5249e8a5ffff472ac961addfe85e1f56e66439981cbad2f7"};
export function decodeCaptureV13History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV13History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v13-image-transport-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV13History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV13Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV13History()).files[relative].source;}
export async function recoverCaptureV13Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV13Source(relative));
}
