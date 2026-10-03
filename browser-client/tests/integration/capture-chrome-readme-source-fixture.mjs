// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v15 CPU fixtures only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical Chrome README source refused');};
const ARCHIVE="c8edd2132afefef5b88fa12a7bac9dc01af76ea1d96edd5dae1f3e406895758a",BEFORE={"browser-client/tests/chrome-journey-defaults.test.mjs":"03a94c9e2a10bb3f9c7d60c898289578a823162bde62a1be95a8825c863a4365","browser-client/tests/integration/capture-reviewed-environment-source-fixture.mjs":"d6a2041c1e813be37b41df55b68d3cfc842c93b4bfba395efcd1819d7726c11c","browser-client/tests/tablet-capture-reviewed-environment-manifest.test.mjs":"fe95e805a89fcae4d3ae09e636ccbb316bc3678740b361ed0123e2b3e6d7c263","browser-client/tests/fixtures/capture-reviewed-environment-v15-complete-source-manifest.json":"c8915cfd0e5291aee811ad4d36d3a63eceed1124ae22a3abe02f7a743b25e3c7","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"bc0cbbb0b5e240a263065ec8aae8a5b99d084e6323ccf3bc96b2106a24e6482b"},CURRENT={"browser-client/tests/chrome-journey-defaults.test.mjs":"57d5cf827f08492c82bc84b7ac97762bec5330f4dff70b33c0681029f534d899","browser-client/tests/integration/capture-reviewed-environment-source-fixture.mjs":"732b579b52d4eeed230dcbad473600c2978898aca79263cd1b96f730581e62ce","browser-client/tests/tablet-capture-reviewed-environment-manifest.test.mjs":"816efa7ebf2f2780631c8c7f585797755e2a64a6dc8c2f6ce043aad01b22319e"};
export function decodeCaptureV15History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV15History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v15-chrome-readme-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV15History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV15Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV15History()).files[relative].source;}
export async function recoverCaptureV15Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV15Source(relative));
}
