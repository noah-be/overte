// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v24 CPU fixtures only. Never imported by production.
import {recoverCaptureV25Input} from './capture-delivery-angle-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical event timing source refused');};
const ARCHIVE="05fe06d808b7b67e1ebbfa8520862d1ad6a306391211949ad9a3428d0ee0157f",BEFORE={"browser-client/tests/fixtures/capture-command-clock-v24-complete-source-manifest.json":"1d5a2cdf8556792c40794c7a8008af07a7b7f101dda800bc70cdd64197bd8f08","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"b2f648e24dd86454a7d85a3c576820f869dfe2ffda6902d40a8fb02acdeca806","browser-client/tests/integration/capture-command-clock-source-fixture.mjs":"e4acbec46a90c258531803dca84a6887ea23a9c524e774b87a36e7d2a92aa11c","browser-client/tests/tablet-capture-command-clock-manifest.test.mjs":"539152738af4d02613659d8e689f85eb713605ef035e00b44507b6305344754a","browser-client/tests/fixtures/embedded-world.ts":"038f463149ac20ca9ee73c23219851d843fe953d26d316ca8a5e763e0c9bb591","browser-client/tests/integration/embedded-world.mjs":"244d7587a90fc436efe740c50e4b0b7f1c65456a8454552bcccc0a9561669305"},CURRENT={"browser-client/tests/integration/capture-command-clock-source-fixture.mjs":"323d0790ad6a280f49e94b48bf5012d55ba7c80466aae0379b52bd5668a055ee","browser-client/tests/tablet-capture-command-clock-manifest.test.mjs":"21418051c8e4e32f5f898b4b3ef005f5a1d9212a9d844489c3d58248c522bc12","browser-client/tests/fixtures/embedded-world.ts":"95d63b3f476c775a762729740b74c96dda52be6845dbe5de4dcefee2ff8818d1","browser-client/tests/integration/embedded-world.mjs":"71a6753cc91f750d3f05114f09c79e65214a63df0e010f0ce23e71a69ee096e1"};
export function decodeCaptureV24History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV24History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v24-event-timing-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV24History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV24Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV24History()).files[relative].source;}
export async function recoverCaptureV24Input(relative,bytes){
 if(Buffer.isBuffer(bytes)&&Object.hasOwn(BEFORE,relative)&&sha(bytes)===BEFORE[relative])return bytes;
 bytes=await recoverCaptureV25Input(relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV24Source(relative));
}
