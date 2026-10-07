// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {admitServedAuthor,AUTHOR_SOURCE_SHA256,AUTHOR_DIAGNOSTICS_SHA256} from './integration/tablet-ptt-native-peer.mjs';
const source=readFileSync(new URL('../lab/native-participant.js',import.meta.url));
const diagnostics=readFileSync(new URL('../gateway/native-avatar-sample-diagnostics.js',import.meta.url));
const peer=readFileSync(new URL('./integration/tablet-ptt-native-peer.mjs',import.meta.url),'utf8');
const sha=b=>createHash('sha256').update(b).digest('hex');
const prefix=Buffer.from('var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS = true;\n');
const composed=mode=>Buffer.concat([prefix,Buffer.from('var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE = '+JSON.stringify(mode)+';\n'),diagnostics,Buffer.from('\n'),source]);
const producer=String.raw`
import ast,json,pathlib,shutil,sys,tempfile,types,base64
source=pathlib.Path(sys.argv[1]);tree=ast.parse((source/'manage.py').read_text())
blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If) and 'OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS' in ast.unparse(n.test)]
assert len(blocks)==1
rows=[]
for value in ('','0','1','passive','PASSIVE','full','true'):
 with tempfile.TemporaryDirectory() as directory:
  root=pathlib.Path(directory);(root/'http').mkdir()
  namespace={'os':types.SimpleNamespace(environ={'OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS':value}),'ROOT':root,'SOURCE':source,'shutil':shutil,'json':json}
  exec(compile(ast.Module(body=[blocks[0]],type_ignores=[]),'<actual-reviewed-author-composition>','exec'),namespace)
  rows.append({'value':value,'bytes':base64.b64encode((root/'http/native-participant.js').read_bytes()).decode()})
print(json.dumps(rows))
`;
test('actual manager-produced declarations authenticate current plain/full/passive bytes without unknown-mode expansion',()=>{
 const rows=JSON.parse(execFileSync('python3',['-B','-c',producer,new URL('../lab/',import.meta.url).pathname],{encoding:'utf8',timeout:5000,maxBuffer:1024*1024}));
 assert.equal(sha(source),'735a5ee9b4327963ea7fb2ebec5e2159c1196aa99d8b6e7fd996809f521b7ede');
 assert.equal(sha(diagnostics),'d59ff56f281fe91c19a16ff36686dcb29767405943023b11a76daa2c5a6a651e');
 for(const row of rows){const bytes=Buffer.from(row.bytes,'base64'),mode=row.value==='1'?'full':row.value==='passive'?'passive':'plain';
  assert.deepEqual(bytes,mode==='plain'?source:composed(mode));
  assert.deepEqual(admitServedAuthor(bytes,{source,diagnostics}),{sourceSHA256:AUTHOR_SOURCE_SHA256,diagnosticsSHA256:AUTHOR_DIAGNOSTICS_SHA256,servedSourceSHA256:sha(bytes),registration:'current-'+mode});
 }
});
test('unknown served modes, duplicated declarations and mixed licensed/current components remain refused',()=>{
 for(const mode of ['','1','PASSIVE','unknown',false,null])assert.throws(()=>admitServedAuthor(composed(mode),{source,diagnostics}));
 const full=composed('full');
 for(const bytes of [Buffer.concat([prefix,full]),Buffer.concat([full,Buffer.from('\n')]),Buffer.concat([prefix,diagnostics,Buffer.from('\n'),source]),Buffer.concat([Buffer.from('var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS = false;\n'),full])])assert.throws(()=>admitServedAuthor(bytes,{source,diagnostics}));
});
test('exact changed current source or sampler is refused even when served bytes match that changed input',()=>{
 for(const delta of ['\n','// private replacement\n']){
  const changedSource=Buffer.concat([source,Buffer.from(delta)]),changedDiagnostics=Buffer.concat([diagnostics,Buffer.from(delta)]);
  assert.throws(()=>admitServedAuthor(changedSource,{source:changedSource,diagnostics}));
  assert.throws(()=>admitServedAuthor(composed('full'),{source,diagnostics:changedDiagnostics}));
 }
});
test('prior current-pin module demonstrably refuses every current plain/full/passive declaration',async()=>{
 const a="export const AUTHOR_SOURCE_SHA256='"+AUTHOR_SOURCE_SHA256+"';",b="export const AUTHOR_DIAGNOSTICS_SHA256='"+AUTHOR_DIAGNOSTICS_SHA256+"';";
 assert.equal(peer.split(a).length-1,1);assert.equal(peer.split(b).length-1,1);
 const old=peer.replace(a,"export const AUTHOR_SOURCE_SHA256='c0648ce3fb6f4924cee122445ef6132e0770d15568b36bcc71aefe8204e0f17f';").replace(b,"export const AUTHOR_DIAGNOSTICS_SHA256='ac3bb49a0ab81913044e1c3c1cde78280098a6b0ff0c59d07f72ede7faba0ca8';");
 const original=await import('data:text/javascript;base64,'+Buffer.from(old).toString('base64'));
 for(const input of [source,composed('full'),composed('passive')])assert.throws(()=>original.admitServedAuthor(input,{source,diagnostics}));
});
test('actual author factory passes exact MyAvatar ownership without probing rates during construction',()=>{
 const text=source.toString(),a=text.indexOf('    var avatarSampleDiagnostics ='),b=text.indexOf('    function report(',a);assert(a>=0&&b>a);
 for(const mode of ['full','passive',undefined])for(const enabled of [false,true]){
  let calls=0,received;const avatar={getDataRate(){throw Error('Unexpected native read');}};
  const c={BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS:enabled,MyAvatar:avatar,print(){},Window:{},location:{isConnected:true},createNativeAvatarSampleDiagnostics:value=>{calls++;received=value;return {};}};
  if(mode!==undefined)c.BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE=mode;
  vm.runInNewContext(text.slice(a,b),c);assert.equal(calls,enabled?1:0);
  if(enabled){assert.equal(received.avatar,avatar);assert.equal(received.mode,mode??'full');assert.equal(received.current(),true);c.location.isConnected=false;assert.equal(received.current(),false);}
 }
});
test('served admission patch leaves whole identity/readback transaction and historical independent pins unchanged',()=>{
 const admission=peer.slice(peer.indexOf('export function admitServedAuthor('),peer.indexOf('\nconst fail='));
 assert(admission.includes("served.length!==13861"));assert(admission.includes('sha(oldAuthor)!==HISTORICAL_AUTHOR_SOURCE_SHA256'));
 assert(admission.includes('sha(oldDiagnostics)!==HISTORICAL_AUTHOR_DIAGNOSTICS_SHA256'));assert(admission.includes('sha(served)!==HISTORICAL_SERVED_SHA256'));
 assert(peer.includes('deadline=since+15000;'));assert(peer.includes('await io.identity();'));assert(peer.includes('observationAfterCommand&&p.observationFresh'));
});
