// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const server=readFileSync(new URL('./server.mjs',import.meta.url),'utf8');
const participant=readFileSync(new URL('../lab/native-participant.js',import.meta.url),'utf8');

test('source-exact builder loads diagnostics only for two reviewed operator values and managed config gates both modes',()=>{
 const guard=server.match(/\+ \((\['1', 'passive'\]\.includes\(process\.env\.OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS\)) \? '\\n' \+ await readFile\(path\.join\(directory, 'native-avatar-sample-diagnostics.js'\)/);
 assert(guard,'source inclusion guard must be the reviewed opt-in predicate');
 const field=server.match(/avatarSampleDiagnostics: (.*?), avatarSampleDiagnosticsMode: (.*?), url:/);assert(field);
 for(const value of [undefined,'','0','1','passive','PASSIVE','true'])for(const publicPlace of [true,false]){
  const context={process:{env:{OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS:value}}};
  const enabled=vm.runInNewContext(guard[1],context);
  assert.equal(enabled,value==='1'||value==='passive');
  const config=vm.runInNewContext('(function(){return {enabled:'+field[1]+',mode:'+field[2]+'};})',context).call({publicPlace});
  assert.equal(config.enabled,!publicPlace&&enabled);assert.equal(config.mode,value==='passive'?'passive':'full');
 }
});

test('actual lab preparation branch preserves disabled bytes and propagates only validated full/passive prefixes',()=>{
 const python=String.raw`
import ast,json,pathlib,shutil,sys,tempfile,types
source=pathlib.Path(sys.argv[1]);tree=ast.parse((source/'manage.py').read_text())
blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If) and 'OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS' in ast.unparse(n.test)]
assert len(blocks)==1
rows=[]
for value in ('','0','1','passive','PASSIVE'):
 with tempfile.TemporaryDirectory() as directory:
  root=pathlib.Path(directory);(root/'http').mkdir()
  namespace={'os':types.SimpleNamespace(environ={'OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS':value}),'ROOT':root,'SOURCE':source,'shutil':shutil,'json':json}
  exec(compile(ast.Module(body=[blocks[0]],type_ignores=[]),'<actual-preparation-branch>','exec'),namespace)
  data=(root/'http/native-participant.js').read_text();ordinary=(source/'native-participant.js').read_text()
  expected='passive' if value=='passive' else 'full'
  enabled=value in ('1','passive')
  prefix='var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS = true;\nvar BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE = '+json.dumps(expected)+';\n'
  rows.append({'value':value,'ordinaryBytes':data==ordinary,'prefixMatched':data.startswith(prefix),'endsWithOriginal':data.endswith(ordinary),'helperIncluded':(source.parent/'gateway/native-avatar-sample-diagnostics.js').read_text() in data})
print(json.dumps(rows))
`;
 const rows=JSON.parse(execFileSync('python3',['-c',python,new URL('../lab/',import.meta.url).pathname],{encoding:'utf8',timeout:10000}));
 for(const row of rows){const enabled=['1','passive'].includes(row.value);assert.equal(row.ordinaryBytes,!enabled);assert.equal(row.prefixMatched,enabled);assert.equal(row.helperIncluded,enabled);assert(row.endsWithOriginal);}
});

test('source-exact author factory receives passive mode with unchanged current/timer/publication locations',()=>{
 const expression=participant.slice(participant.indexOf('    var avatarSampleDiagnostics ='),participant.indexOf('    function report('));
 for(const mode of ['passive','full',undefined]){
  let received;
  const context={BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS:true,createNativeAvatarSampleDiagnostics:config=>{received=config;return {};},print(){},Window:{},Stats:{},location:{isConnected:true}};
  if(mode!==undefined)context.BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE=mode;
  vm.runInNewContext(expression,context);assert.equal(received.mode,mode??'full');assert.equal(received.current(),true);
 }
 assert(participant.includes('}, 2000);'));assert(participant.includes('}, 500);'));
 assert(participant.includes('report("command-applied", command);\n            if (avatarSampleDiagnostics) avatarSampleDiagnostics.authorObservation();'));
});
