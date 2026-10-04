// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole historical v26 CPU fixtures only. Never imported by production.
import {recoverCaptureV27Input} from './capture-avatar-flow-source-fixture.mjs';
import {open,realpath} from 'node:fs/promises';import {constants} from 'node:fs';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical delivery and ANGLE source refused');};
const ARCHIVE="7ba538ec0cc6c4ce352ac670e8b4c926cd9cc0fcc5f49c2aa30f49831e286271",BEFORE={"browser-client/tests/fixtures/capture-delivery-angle-v26-complete-source-manifest.json":"a366564b2ec15d802d0981e67327e1bb702212dc2c1ee1472371bc59f2ee7c3d","browser-client/tests/integration/capture-delivery-angle-source-fixture.mjs":"e4951061d28a70629cc821b9ae627138b1b7316da62b262ece67b0ce9242cad5","browser-client/tests/tablet-capture-delivery-angle-manifest.test.mjs":"bb6ac7162961d801a3d2a29b2ca982c55e936da4ce6c19fdeee95e78e20f388f","browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs":"0572f416b5d5b28a7ebf393015395aa0b68d96035af60a89effbd31640562abe",".github/workflows/browser-client.yml":"d608f4173399093959bda9362953a46589d02b08893cc5468c0c09c0de358202","browser-client/tests/embedded-world-angle-request.test.mjs":"e74491294407efa86e27ab2f93eec46b7ff621f2497fce207e6bf9fd12260a1e","browser-client/gateway/server.mjs":"6d5d81332a41a66df667fa1f8d75a5bbd1c29a345ccbb85fcb75e89419642099","browser-client/tests/integration/real-session.mjs":"ca8f8f6502e569c130625ca72403b0a1bf145ac227645a16af88bb43aa7f94a7","browser-client/lab/curate-core-journey.py":"e6cf19232d627a7daa232cb299e365f4b2154b06bbf36f1946ce72f564ccb3e6","browser-client/lab/manage.py":"84b4426187e078515b77984a3581a63130d2dbc0c5edf4230a66a17ecdbf8e66","browser-client/tests/fixtures/avatar-delivery-source-fixture.mjs":"b26d984a8c0af91e3ea80303d7b05422ae7a7f9eda42ba2536a10cff91c8dfdb","browser-client/tests/avatar-delivery-source-fixture.test.mjs":"2c789e1d020e596372d6faa6bb5ac3af4fedf350f7bec0264b571ac2832b3b5a","browser-client/tests/native-avatar-curation.test.mjs":"6750521df33bac1447c05450ba674ce67e2c9a9de8e86ad63ffefc39311b9ee5","browser-client/gateway/native-avatar-delivery.test.mjs":"390532d3e0afc46ce923e1572e38964ccf25283b3f1b8da1887d2414581f5ca8"},CURRENT={"browser-client/tests/integration/capture-delivery-angle-source-fixture.mjs":"2e60df8e99cb6dfe0a1dbc634c0b40f2ea7b28e477c86fe777e0e8d2c332a16d","browser-client/tests/tablet-capture-delivery-angle-manifest.test.mjs":"fde35997bde0c71e13a623a51ffcc081dd2e67eb94a9def2dc458265729c21d3",".github/workflows/browser-client.yml":"5ef53a7c48d502b8c64d0d22042a50a5ac37c15c35b55fde9149deaa2e768a20","browser-client/tests/embedded-world-angle-request.test.mjs":"e1d7d93dff0313afa884420d3b77f1a4b8bc10524ca669a2a6111413f2fb834e","browser-client/gateway/server.mjs":"116c45aae6ca9587b546e92bb88b4bd5472ff5100226994b0fced3c80263f45f","browser-client/tests/integration/real-session.mjs":"ec4ac0fb187acbcd650c10295c5c5364a00687c3abab1e24f395934d3a3460a7","browser-client/lab/curate-core-journey.py":"915a9d02a812aad92192cf650c3899dd27b1fcb22537f3edf60bd1e2f846da81","browser-client/lab/manage.py":"53cd7fcce5887c993bc724ce3e391c4c7d0975f338ed1c96a1adfdbe7c9bdb95","browser-client/tests/fixtures/avatar-delivery-source-fixture.mjs":"b26d984a8c0af91e3ea80303d7b05422ae7a7f9eda42ba2536a10cff91c8dfdb","browser-client/tests/avatar-delivery-source-fixture.test.mjs":"d6e2709189ef03e55ab7bff06e0e4b1f42ce89b43d27af4b141aed254857db79","browser-client/tests/native-avatar-curation.test.mjs":"d04e832c93d14282b3a1ce3283dfe33dd27ddb7dcd5cb54792e4d3f4e7916b9f","browser-client/gateway/native-avatar-delivery.test.mjs":"f5321d7dc990a771a3ad30d0547089cd7248c0b6a2575e5037c7e32a085425cd"},EXTERNAL_CURRENT={"browser-client/lab/atomic-provisioning/fixtures/managed-ancestry-before.json.gz":"5b1870bc3583da9bca904e1c76fdd900f11ee02f569eb9a7b93395b8b1b9302c","browser-client/lab/atomic-provisioning/fixtures/managed-ancestry-original84-bodies.json":"cf9a324b544cd6ef005cbcb52a8829641ecaca7b3ba07e5b881e1eba1ffa77b7","browser-client/lab/atomic-provisioning/fixtures/managed-ancestry-replay-inputs.json":"10b719060a9b66d3b7328dea403aa11803e46d21788b1bb0b36875f3ef7264d6","browser-client/lab/atomic-provisioning/fixtures/managed-seven-manage-recovery.json":"e471f11465d9575c316decd0c6e9d91c5200d05de6531474c590993501e79109","browser-client/lab/atomic-provisioning/managed_ancestry_history.py":"3a496328a4cb17a74833c451f05f1ffa51c91149ec3965a7e9f92777fd81bdf2","browser-client/lab/atomic-provisioning/source-pins.json":"709fafd17508b5a275a82a78f13f58f57b07686746c2cc453635d4a70db808b9","browser-client/lab/atomic-provisioning/test_managed_ancestry_history.py":"b51ff02b440a723f80b1d7d6f7be0e91282a9c4af326cddf076cd97159746de1","browser-client/lab/atomic-provisioning/test_managed_composition.py":"31c587e7ba721c3d6e083a77daa7ab5c70591b56b019b5283aefd61abbb63fb3","browser-client/lab/manage.py":"53cd7fcce5887c993bc724ce3e391c4c7d0975f338ed1c96a1adfdbe7c9bdb95","browser-client/lab/test_manage_state.py":"103ee00b456fefeb262b5cce7a4b9738dab219077bb4d62aa5b1cf3a102c46c2","browser-client/lab/test_managed_ancestry.py":"6959505a9b12f4b9ce296a5947e9ec96841fc729db7d6a3de77c0139bcad0d06","browser-client/lab/test_managed_ancestry_owned_cpu.py":"fc2c695eaa4be889ed19e72e1e8dc92212f4402487fa3ad1566906a5bac6df85"},HISTORICAL={};
export function decodeCaptureV26History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>131072||sha(bytes)!==ARCHIVE)refuse();
 const value=JSON.parse(gunzipSync(bytes,{maxOutputLength:524288}));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,version'||Object.keys(value.files||{}).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const[key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 Object.freeze(value.files);return Object.freeze(value);
}
let history;
export async function readCaptureV26History(){
 if(!history)history=(async()=>{const file=fileURLToPath(new URL('../fixtures/capture-v26-software-managed-before.json.gz',import.meta.url));if(await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>131072)refuse();const b=Buffer.alloc(131073);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>131072||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return decodeCaptureV26History(b.subarray(0,n));}finally{await h.close();}})();return history;
}
export async function readCaptureV26Source(relative){if(!Object.hasOwn(BEFORE,relative))refuse();return(await readCaptureV26History()).files[relative].source;}
export async function recoverCaptureV26Input(relative,bytes){
 bytes=await recoverCaptureV27Input(relative,bytes);
 if(!Buffer.isBuffer(bytes))refuse();if(!Object.hasOwn(CURRENT,relative))return bytes;
 const hash=sha(bytes);if(hash===BEFORE[relative]||HISTORICAL[relative]?.includes(hash))return bytes;if(hash!==CURRENT[relative])refuse();return Buffer.from(await readCaptureV26Source(relative));
}


export async function readCurrentSoftwareManagedSource(relative,input){
 const expected=Object.hasOwn(CURRENT,relative)?CURRENT[relative]:EXTERNAL_CURRENT[relative];if(!expected)refuse();
 const file=input instanceof URL?fileURLToPath(input):input;if(typeof file!=='string'||await realpath(file)!==file)refuse();
 const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const a=await h.stat();if(!a.isFile()||a.uid!==process.getuid()||a.nlink!==1||(a.mode&0o022)||!Number.isSafeInteger(a.size)||a.size<1||a.size>262144)refuse();
 const b=Buffer.alloc(262145);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}
 const z=await h.stat();if(n!==a.size||n>262144||!['dev','ino','size','uid','mode','nlink','mtimeMs','ctimeMs'].every(k=>a[k]===z[k]))refuse();const recovered=await recoverCaptureV27Input(relative,b.subarray(0,n));if(sha(recovered)!==expected)refuse();return recovered;
 }finally{await h.close();}
}

export async function prepareAvatarV26HistoryReaders(originalReadFileSync,originalReadReviewed,originalRecover){
 const entries=await Promise.all(['browser-client/lab/manage.py','browser-client/gateway/server.mjs','browser-client/tests/integration/real-session.mjs','browser-client/lab/curate-core-journey.py'].map(async relative=>{
  const url=new URL('../../'+relative.replace(/^browser-client\//,''),import.meta.url);
  await readCurrentSoftwareManagedSource(relative,url);
  const before=Buffer.from(await readCaptureV26Source(relative));
  return [url.href,{before,reviewed:relative==='browser-client/lab/manage.py'?before:originalRecover(relative,before)}];
 }));
 const fixed=new Map(entries),format=(bytes,encoding)=>encoding===undefined?Buffer.from(bytes):encoding==='utf8'?bytes.toString('utf8'):refuse();
 return Object.freeze({
  readFileSync:(input,encoding)=>input instanceof URL&&fixed.has(input.href)?format(fixed.get(input.href).before,encoding):originalReadFileSync(input,encoding),
  readReviewedAvatarSource:(input,encoding)=>input instanceof URL&&fixed.has(input.href)?format(fixed.get(input.href).reviewed,encoding):originalReadReviewed(input,encoding)
 });
}
