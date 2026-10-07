
// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {copyCaptureFixtureRow as originalLookaheadCopy,readCaptureHistoricalPreparer as originalLookaheadPreparer,readCaptureV6History,decodeCaptureV6History,decodeCaptureSourceHistory} from './capture-lookahead-source-fixture.mjs';
export {readCaptureV6History,decodeCaptureV6History,decodeCaptureSourceHistory};
import {recoverCaptureV8Input} from './capture-status-source-fixture.mjs';
import {open,realpath,writeFile} from 'node:fs/promises';import {constants} from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
const sha=b=>createHash('sha256').update(b).digest('hex'),refuse=()=>{throw Error('Historical readback source refused');};
async function bounded(file,max){if(path.resolve(file)!==file||await realpath(file)!==file)refuse();const h=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const a=await h.stat();if(!a.isFile()||a.size<1||a.size>max)refuse();const b=Buffer.alloc(max+1);let n=0;while(n<b.length){const r=await h.read(b,n,b.length-n,n);if(!r.bytesRead)break;n+=r.bytesRead;}const z=await h.stat();if(n!==a.size||n>max||a.ino!==z.ino||a.dev!==z.dev||a.size!==z.size||a.mtimeMs!==z.mtimeMs||a.ctimeMs!==z.ctimeMs)refuse();return recoverCaptureV8Input(path.relative(fileURLToPath(new URL('../../',import.meta.url)),file),b.subarray(0,n));}finally{await h.close();}}
// Version7 history is a CPU fixture input, never a production admission path.
import vm from 'node:vm';
import {AUDIO_SCRIPT_SHA256,AUDIO_RCC_SHA256} from '../../gateway/browser-capture-overrides.mjs';
export {AUDIO_SCRIPT_SHA256,AUDIO_RCC_SHA256};
const V7_ARCHIVE="1018f171330b0174894c53e5e989c03066db17d07a699df3f7632fcedf26d1d4",V7_BEFORE={"gateway/native-browser-capture.js":"1d258ce76705033598e3f5decbe084e746feb2bcd19ba30f8b0c1afa416d6f2f","gateway/browser-capture-overrides.mjs":"9a41d28676ada36d6a54bec5186214963d9864f6cad8c79e7abe666f9d36d7fe","gateway/browser-capture.test.mjs":"0cda7142dd4dc51dd188ff78a13aacdcf8367905028b6c5e9fc802c46816be6c","tests/integration/capture-source-fixture.mjs":"518b2bee68d61396a968a2754fb2e5e9e7bd5868b8ee562cdd0f1236e1369664","tests/integration/capture-lookahead-source-fixture.mjs":"c3b0afaf2fb666fe49a3349da60426c73f0b44a9585f09852b9bb90a501b27cd","tests/integration/prepare-tablet-capture-acceptance.mjs":"aba9987b7939b236e27e93d14a869f8e1248d7063796a6cd025425d9105b2409","tests/tablet-capture-style.test.mjs":"26184206a3f39e42bcae68eff06cbe985cd412f8122deb08fd7f813ea2f35fef","tests/tablet-capture-switch-width.test.mjs":"2ccb87e96756e48a6619a74fd7b5a488c399e63578ca1c072e885d71f307bc3d","tests/tablet-capture-fst-escape-manifest.test.mjs":"19a8faaa5d04511c8b53e02ebe7d924fc81c6f72f3f82830f8a5b425362ac97f","tests/tablet-capture-world-key-manifest.test.mjs":"f761e5b2d30c86202b6187ce41c703a89cc67fe28e11ae9dc721b65b61e50661"},V7_CURRENT={"gateway/native-browser-capture.js":"ba6d32f99acc960a9539c19faba5cdc8d6ad005f73f927b49a0941df247979c3","gateway/browser-capture-overrides.mjs":"38aa8a75aeca858af220f98a020fc6ab806b5611a28c6d3da1ea377b0e6f40bc","gateway/browser-capture.test.mjs":"aea4777a77ec45521113d0b0420e189fe59c09427ffb928de1a73b8d1fce9190","tests/integration/capture-source-fixture.mjs":"eb4dc8764b9db77cec674710c67504ff9df3f04e43aadf2bcfd086a8136a4ca1","tests/integration/capture-lookahead-source-fixture.mjs":"0f0a99dbd92025346bb6dd40bf8c0e2e0a064f1eddf1ed707d2b05a14ecc4ab8","tests/tablet-capture-style.test.mjs":"235979f6d71c0b042bff5b44027d36f4ebbdc83427ddd5b8e4973cc96abd7783","tests/tablet-capture-switch-width.test.mjs":"9065766ffc07415bd3650e9ce98b238f0e5087075a6f829b9ef9a6cbe7109303","tests/tablet-capture-fst-escape-manifest.test.mjs":"36f3eec12811a360ab91c8846fdec7827098d03a092e85da499cfa20986ae69a","tests/tablet-capture-world-key-manifest.test.mjs":"39110eefee67b787eaf92ab08dd815af720eeeabc5553db4e27b49185283de12"};
export function decodeCaptureV7History(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>65536||sha(bytes)!==V7_ARCHIVE)refuse();
 const b=gunzipSync(bytes,{maxOutputLength:262144}),v=JSON.parse(b);
 if(!v||v.version!==1||Object.keys(v).sort().join(',')!=='files,version'||Object.keys(v.files||{}).sort().join(',')!==Object.keys(V7_BEFORE).sort().join(','))refuse();
 for(const[k,hash]of Object.entries(V7_BEFORE)){const r=v.files[k];if(!r||Object.keys(r).sort().join(',')!=='sha256,source'||r.sha256!==hash||typeof r.source!=='string'||sha(Buffer.from(r.source))!==hash)refuse();Object.freeze(r);}
 Object.freeze(v.files);return Object.freeze(v);
}
export async function readCaptureV7History(){return decodeCaptureV7History(await bounded(fileURLToPath(new URL('../fixtures/capture-v7-readback-before.json.gz',import.meta.url)),65536));}
export async function readCaptureV7Source(relative){
 if(!Object.hasOwn(V7_CURRENT,relative))refuse();
 const file=fileURLToPath(new URL('../../'+relative,import.meta.url)),b=await bounded(file,2097152);
 if(sha(b)!==V7_CURRENT[relative])refuse();return(await readCaptureV7History()).files[relative].source;
}
export async function readCaptureHistoricalPreparer(version){if(version===7)return(await readCaptureV7History()).files['tests/integration/prepare-tablet-capture-acceptance.mjs'].source;return originalLookaheadPreparer(version);}
export async function copyCaptureFixtureRow(options){
 const{client,relative,dest,expectedSHA256,version}=options;
 const olderReadback=[4,5].includes(version)&&['gateway/native-browser-capture.js','gateway/browser-capture.test.mjs'].includes(relative);
 if(!olderReadback&&version!==7&&!(version===6&&Object.hasOwn(V7_CURRENT,relative)))return originalLookaheadCopy(options);
 if(typeof relative!=='string'||! /^(?:src|shared|gateway|tests|native-input|tools)\/[A-Za-z0-9_.\/-]+$/.test(relative)||relative.split('/').includes('..')||typeof expectedSHA256!=='string'||! /^[a-f0-9]{64}$/.test(expectedSHA256))refuse();
 const root=path.resolve(client);if(await realpath(root)!==root)refuse();const b=await bounded(path.join(root,relative),2097152),hash=sha(b);
 let output=b;
 if(hash!==expectedSHA256){
  // Version6 already has a separately pinned pre-FST core. Preserve that recovery.
  if(version===6&&['tests/integration/capture-source-fixture.mjs','tests/tablet-capture-world-key-manifest.test.mjs'].includes(relative)&&expectedSHA256!==V7_BEFORE[relative]){const row=(await readCaptureV6History()).files[relative];if(!row||row.sha256!==expectedSHA256||![V7_CURRENT[relative],V7_BEFORE[relative]].includes(hash))refuse();output=Buffer.from(row.source);}
  else{
  if(!Object.hasOwn(V7_CURRENT,relative)||hash!==V7_CURRENT[relative]||expectedSHA256!==V7_BEFORE[relative])refuse();
  output=Buffer.from((await readCaptureV7History()).files[relative].source);
  }
 }
 if(sha(output)!==expectedSHA256||path.resolve(dest)!==dest||await realpath(path.dirname(dest))!==path.dirname(dest))refuse();await writeFile(dest,output,{mode:0o600,flag:'wx'});
}
// Evaluate only the exact whole archived generator after validating the actual current generator.
// Original style/width tests use these historical inputs; v8 tests exercise actual current code.
const historicalFactory=await readCaptureV7Source('gateway/browser-capture-overrides.mjs');
const factoryStart=historicalFactory.indexOf('export function buildBrowserCaptureUI('),factoryEnd=historicalFactory.indexOf('\nexport async function loadBrowserCapturePackage',factoryStart);
if(factoryStart<0||factoryEnd<=factoryStart)refuse();
const factoryContext={createHash,AUDIO_SCRIPT_SHA256,URL,path,fileURLToPath,once:(source,a,b)=>{if(source.split(a).length!==2)refuse();return source.replace(a,b);}};
vm.runInNewContext(historicalFactory.slice(factoryStart,factoryEnd).replace(/^export /,'')+';this.generate=buildBrowserCaptureUI;',factoryContext);
export const buildBrowserCaptureUI=factoryContext.generate;
