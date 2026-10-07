// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// CPU test-fixture inputs only. Never used by runtime admission or the preparer.
import {recoverCaptureV8Input} from './capture-status-source-fixture.mjs';
import {open,realpath,writeFile} from 'node:fs/promises';import {constants} from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),refuse=()=>{throw Error('Historical capture source refused');};
const ARCHIVE_SHA256="65f09bc5c7c92597abb6e877b1c5a85b26749f8a116724e7387600dc40639fb9",CURRENT={"gateway/native-tablet.js":"3f21000d280e6747ed032fe2183bd76512cbb521b6bcd3416db22b7b58e57bb3","gateway/tablet.mjs":"c658e82e0446d97e5d100234c878df2b835883a730081cba58856be86cbf051f","src/main.ts":"8059c8e774e9f641d85f0255dcd6e37f0143cf005a7dcb5a4d7d714eedca4ac4","src/tablet-protocol.ts":"8e88c7ddbc9d7dbfe6bfc1a514992c5f5eb4bdc3ad086cdd95cd3ddd4f6b6c3f","src/tablet.ts":"6bff82a459b0b2b3a2c6f0c8abc0ba120dc89976a5215ff2c537f7c5c63a28b4","tests/tablet-capture-layout-manifest.test.mjs":"aedbd44493a831edade94b511d7bb3263a8e04b9f2f082dd2e8f2b40005e47a0","tests/tablet-capture-reacquisition-manifest.test.mjs":"be273205c43c1be072fe6a04e57a4ef0de2e083f64cffdb955633985411d4c8c","gateway/browser-capture-overrides.mjs":"38aa8a75aeca858af220f98a020fc6ab806b5611a28c6d3da1ea377b0e6f40bc","tests/tablet-capture-style.test.mjs":"235979f6d71c0b042bff5b44027d36f4ebbdc83427ddd5b8e4973cc96abd7783"},BEFORE={"gateway/native-tablet.js":"0c90732c34a8b06dc5ce1112697ac1a4f6f88a5a20754d21a71a42ee7f3b8eb4","gateway/tablet.mjs":"3f332c951c7225478c67765fd102d295d30bcff832551e5088d09b95e54d4ba5","src/main.ts":"f33b27cab252aff9f194fc64d9a9b4ae942ec77f79e04f91d1597b61afe55324","src/tablet-protocol.ts":"006e304a3e5a03d7a762d7b64e4ec8b24c46796340e00178c3264dedf6f9c8c1","src/tablet.ts":"04e91da914725e290d56dbeb2b5e837a2d7f9233d455eda88e4ca30e21c9e92e","tests/tablet-capture-reacquisition-manifest.test.mjs":"f252f68b2a8d29ff4c26c5103d4bdd3895e1649471767bd6e9c6bb98b3cbcc71","tests/tablet-capture-layout-manifest.test.mjs":"4ad007f181524d50308a4aae257115b21a0e44010e777aea628f12748799cae2","gateway/browser-capture-overrides.mjs":"661347b2b9e27f18ce1cebf2f88fa3d853a7646f236818a7f93dc08cede48f52","tests/tablet-capture-style.test.mjs":"6d7095041c22aeb579d5a94679c86d69bc27ccfebf50c0b4b45af1f0b3ec2826"};
CURRENT["tests/tablet-capture-switch-width.test.mjs"]="9065766ffc07415bd3650e9ce98b238f0e5087075a6f829b9ef9a6cbe7109303";BEFORE["tests/tablet-capture-switch-width.test.mjs"]="3a50f37c6e3e70e5e60803e473c4d7d938f6b30bc2cae8e344b99cda175d8eee";
const PREPARER_SHA256="ff1430f16e58a837d969e2d2e860ff902f4c8bf7f6b1f4cd61416fbcb8fe2d30";
const V4={
 'src/audio.ts':['capture-reacquisition-v4-audio.ts.txt','8e60d96fb9d9ead5ea840b4a27ac1d363f0166090ddcc66fec375e3737dd6303','99fa5cda1b6e571872f07162bedd850382dabad9d95044704d886f9a40ea000d'],
 'src/browser-capture-target.ts':['capture-reacquisition-v4-target.ts.txt','6ba823e20d42a09342b5a8322990916f896aaf17ef5290e5218ce50941973cac','888d45a66279fe17d6231a119c15757858fe78feee5438b223f7013c838b272a'],
 'src/browser-capture-audio.test.ts':['capture-reacquisition-v4-audio-test.ts.txt','ad8e9c4207e26eaa0b828311ce126c73703e962d25f503b30d0477ae48d55751','f75252b1e4065b792c1b28788f277ace46e6fac9ecfbdc5cd5daec34a51637d7'],
 'tests/tablet-capture-layout-manifest.test.mjs':['capture-reacquisition-v4-layout-test.mjs.txt','e6af72e4057fde66de0c088fdda3ac1c01600fb628b37fbbdae7a0473f4a9211',CURRENT['tests/tablet-capture-layout-manifest.test.mjs']]
};
async function readBounded(file,max){
 if(path.resolve(file)!==file||await realpath(file)!==file)refuse();
 const handle=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const before=await handle.stat();if(!before.isFile()||before.size>max||before.size<1)refuse();const bytes=Buffer.alloc(max+1);let count=0;while(count<bytes.length){const read=await handle.read(bytes,count,bytes.length-count,count);if(!read.bytesRead)break;count+=read.bytesRead;}const after=await handle.stat();if(count!==before.size||count>max||after.ino!==before.ino||after.dev!==before.dev||after.size!==before.size||after.mtimeMs!==before.mtimeMs||after.ctimeMs!==before.ctimeMs)refuse();return recoverCaptureV8Input(path.relative(fileURLToPath(new URL('../../',import.meta.url)),file),bytes.subarray(0,count));}finally{await handle.close();}
}
export function decodeCaptureSourceHistory(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>65536||sha(bytes)!==ARCHIVE_SHA256)refuse();
 const decoded=gunzipSync(bytes,{maxOutputLength:262144});if(decoded.length<1||decoded.length>262144)refuse();const value=JSON.parse(decoded.toString('utf8'));
 if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='files,preparer,version'||!value.files||Object.keys(value.files).sort().join(',')!==Object.keys(BEFORE).sort().join(','))refuse();
 for(const [key,hash]of Object.entries(BEFORE)){const row=value.files[key];if(!row||Object.keys(row).sort().join(',')!=='sha256,source'||row.sha256!==hash||typeof row.source!=='string'||sha(Buffer.from(row.source))!==hash)refuse();Object.freeze(row);}
 const p=value.preparer;if(!p||Object.keys(p).sort().join(',')!=='sha256,source'||p.sha256!==PREPARER_SHA256||typeof p.source!=='string'||sha(Buffer.from(p.source))!==PREPARER_SHA256)refuse();Object.freeze(p);Object.freeze(value.files);return Object.freeze(value);
}
let archive;
async function history(){if(!archive)archive=readBounded(fileURLToPath(new URL('../fixtures/capture-source-history-v5-world-key.json.gz',import.meta.url)),65536).then(decodeCaptureSourceHistory);return archive;}
export async function readCaptureHistoricalPreparer(version){
 if(version!==4&&version!==5)refuse();if(version===5)return(await history()).preparer.source;
 const bytes=await readBounded(fileURLToPath(new URL('../fixtures/capture-reacquisition-v4-prepare.mjs.txt',import.meta.url)),65536);if(sha(bytes)!=='80c2ce58e464ae7f91755d6493fccd8046105bfd0dd80ea9c86af4d33dce02bd')refuse();return bytes.toString();
}
export async function copyCaptureFixtureRow({client,relative,dest,expectedSHA256,version}){
 if([4,5].includes(version)&&['gateway/native-browser-capture.js','gateway/browser-capture.test.mjs'].includes(relative))return(await import('./capture-readback-source-fixture.mjs')).copyCaptureFixtureRow({client,relative,dest,expectedSHA256,version});
 if(![4,5,6].includes(version)||typeof relative!=='string'||! /^(?:src|shared|gateway|tests|native-input|tools)\/[A-Za-z0-9_.\/-]+$/.test(relative)||relative.split('/').includes('..')||typeof expectedSHA256!=='string'||! /^[a-f0-9]{64}$/.test(expectedSHA256))refuse();
 const root=path.resolve(client);if(await realpath(root)!==root)refuse();const file=path.join(root,relative);let bytes=await readBounded(file,2097152);const current=sha(bytes);
 if(current!==expectedSHA256){
  if(version===6)refuse();
  const gold=version===4?V4[relative]:null;
  if(gold){if(gold[1]!==expectedSHA256||gold[2]!==current)refuse();bytes=await readBounded(path.join(root,'tests/fixtures',gold[0]),2097152);if(sha(bytes)!==gold[1])refuse();}
  else{if(BEFORE[relative]!==expectedSHA256||CURRENT[relative]!==current)refuse();const row=(await history()).files[relative];bytes=Buffer.from(row.source);if(sha(bytes)!==expectedSHA256)refuse();}
 }
 if(path.resolve(dest)!==dest||await realpath(path.dirname(dest))!==path.dirname(dest))refuse();await writeFile(dest,bytes,{mode:0o600,flag:'wx'});
}
