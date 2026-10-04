// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v23 CPU fixtures only. Never imported by production.
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical command clock source refused');};
const ARCHIVE="f2c9d99427d41342523f50dc91ce351cc8edcb4be60f121728dabadc67633d82",BEFORE={"browser-client/tests/fixtures/capture-live-context-v23-complete-source-manifest.json":"b126e6098be4b0619513432c7c384969aff569e163fa28405d816c758640f1c5","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"a13f60c0683ada6ae4a41be149a4b059eb3a00c302da79bb7180eada87b9ed41","browser-client/tests/integration/capture-live-context-source-fixture.mjs":"67205f0f15a35cfab0f22f6e0585b9a9333d25fab1df31159bf441f17845cd83","browser-client/tests/tablet-capture-live-context-manifest.test.mjs":"ff9d70b40626a9ed35f8862185944e0a5104b151c6155d8e32137f9a119ad258","browser-client/lab/curate-core-journey.py":"3980961dde13cb9c26b1dbcc0ed2d733cc9aeebe5068347704f6d891e652bc36"},CURRENT={"browser-client/tests/integration/capture-live-context-source-fixture.mjs":"0d580dd51ba4604652d5d195e3db97df0f1cc86c51866270036009b59aa9200d","browser-client/tests/tablet-capture-live-context-manifest.test.mjs":"516411d5ecac666e3aaa224e15ea1ea783f6f36f98f2c419085eb2f2500fe574","browser-client/lab/curate-core-journey.py":"d879087afc510171c0e131c69ca40fd5127c77bbe78f6d8f86a4749c3cfb55b4"};
export function decodeCaptureV23History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV23History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v23-command-clock-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV23History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV23Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV23History()).files[relative].source;}
export async function recoverCaptureV23Input(relative,bytes){
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative])return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV23Source(relative));
}

// Current curator is an explicitly authenticated external Chrome20 dependency,
// outside the unchanged production capture-row regex. No historical imports.
export async function readCurrentCommandClockCurator(file){
 if(typeof file!=='string'||await realpath(file)!==file)refuse();
 const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const a=await h.stat();if(!a.isFile()||a.nlink!==1||a.uid!==process.getuid()||a.size<1||a.size>65536)refuse();
 const b=Buffer.alloc(65537);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
 const z=await h.stat();if(n!==a.size||n>65536||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs||sha(b.subarray(0,n))!==CURRENT['browser-client/lab/curate-core-journey.py'])refuse();return b.subarray(0,n);
 }finally{await h.close();}
}
