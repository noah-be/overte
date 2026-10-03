// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Pure declaration/admission controls: no worker, namespace or network launch.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm,symlink} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {sandboxCommand,workerEnvironment} from './worker-sandbox.mjs';
import {networkWorkerEnvironment} from './network-worker-environment.mjs';

const admission = fileURLToPath(new URL('../tools/trusted-network/src/owner_admission.py',import.meta.url));
const validate = `import importlib.util,json,sys
s=importlib.util.spec_from_file_location('owned_admission',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
c,p,a,filesystem=json.load(sys.stdin)
try:
 r=m.validate(c,p,a,filesystem=filesystem)
 print(json.dumps({'admitted':True,'unchangedNativeTail':r['args'][-1]==c['args'][-1]}))
except m.Refusal as e:
 print(json.dumps({'admitted':False,'refusal':e.args[0]}))
`;
function check(record,filesystem=false) {
 const result=spawnSync('/usr/bin/python3',['-B','-c',validate,admission],{
  input:JSON.stringify([record.config,record.policy,record.attestation,filesystem]),encoding:'utf8',timeout:5000,maxBuffer:4096});
 assert.equal(result.status,0);assert.equal(result.stderr,'');return JSON.parse(result.stdout);
}
async function fixture(body) {
 const directory=await mkdtemp('/tmp/overte-browser-admission-');
 const root=await mkdtemp('/tmp/overte-runtime-admission-');
 try {
  const executable=path.join(root,'interface');
  await mkdir(path.join(root,'scripts/system'),{recursive:true});
  await writeFile(executable,'non-executed owned native fixture');
  await writeFile(path.join(directory,'machine-id'),'a'.repeat(32)+'\n');
  await writeFile(path.join(directory,'network-resolv.conf'),'nameserver 10.0.2.3\n');
  const overrides=[];
  for(const [sourceName,targetName]of [['browser-emote.js','emote.js'],['browser-audio.js','audio.js']]) {
   const source=path.join(directory,sourceName),target=path.join(root,'scripts/system',targetName);
   await writeFile(source,'owned generated script');await writeFile(target,'owned installed script');overrides.push({source,target});
  }
  const env=workerEnvironment(directory,{LIBGL_ALWAYS_SOFTWARE:'1',PULSE_SERVER:'unix:'+directory+'/pulse.socket'});
  Object.assign(env,{DISPLAY:':1234',XAUTHORITY:path.join(directory,'Xauthority')});
  const produce=readOnlyOverrides=>sandboxCommand({directory,executable,env,roots:[root],display:1234,readOnlyOverrides});
  const worker=await produce(overrides),args=[...worker.args];
  // Exact existing launchNativeNetwork resolver substitution; no helper launch.
  args[args.indexOf('/etc/resolv.conf')]=path.join(directory,'network-resolv.conf');
  const config={command:worker.command,args,environment:networkWorkerEnvironment(args),bridgePort:8090,
   bridgeSocket:path.join(directory,'native-network.socket'),supervisorParentPID:42};
  const policy={version:1,hostUID:process.getuid(),hostGID:process.getgid(),sessionParent:'/tmp',
   nativeExecutables:[executable],nativeReadRoots:[root]};
  const attestation={version:1,hostUID:policy.hostUID,hostGID:policy.hostGID,parentPID:42,userNS:[1,2],netNS:[1,3],routes:12};
  await body({directory,root,executable,overrides,produce,config,policy,attestation});
 }finally{await rm(directory,{recursive:true,force:true});await rm(root,{recursive:true,force:true});}
}
test('current worker-produced Audio and Emote declarations pass immutable admission together',async()=>fixture(async r=>{
 const before=JSON.stringify(r.config);assert.deepEqual(check(r),{admitted:true,unchangedNativeTail:true});
 assert.equal(JSON.stringify(r.config),before);
}));
test('each current adapter is admitted independently without granting another script',async()=>fixture(async r=>{
 for(const removed of r.overrides){
  const config=structuredClone(r.config),i=config.args.indexOf(removed.source);config.args.splice(i-1,3);
  assert.deepEqual(check({...r,config}),{admitted:true,unchangedNativeTail:true});
 }
}));
test('original worker boundary without adapters remains admitted',async()=>fixture(async r=>{
 const config=structuredClone(r.config);
 for(const removed of r.overrides){const i=config.args.indexOf(removed.source);config.args.splice(i-1,3);}
 assert.deepEqual(check({...r,config}),{admitted:true,unchangedNativeTail:true});
}));
test('unknown source name and swapped or foreign destination still refuse',async()=>fixture(async r=>{
 for(const [source,target]of [[path.join(r.directory,'unknown.js'),r.overrides[0].target],
  [r.overrides[0].source,r.overrides[1].target],[r.overrides[0].source,'/opt/foreign/scripts/system/emote.js']]){
  const config=structuredClone(r.config),i=config.args.indexOf(r.overrides[0].source);config.args[i]=source;config.args[i+1]=target;
  assert.deepEqual(check({...r,config}),{admitted:false,refusal:'unapproved-bind'});
 }
}));
test('current worker refuses generated-source and installed-target aliases',async()=>fixture(async r=>{
 const alias=path.join(r.directory,'alias');await symlink(r.directory,alias);
 await assert.rejects(r.produce([{source:path.join(alias,'browser-audio.js'),target:r.overrides[1].target}]),/Only reviewed|canonical/);
 const targetAlias=path.join(r.root,'scripts-alias');await symlink(path.join(r.root,'scripts'),targetAlias);
 await assert.rejects(r.produce([{source:r.overrides[1].source,target:path.join(targetAlias,'system/audio.js')}]),/Only reviewed|canonical/);
}));
test('immutable admission rejects an exact named generated-source symlink before other filesystem reads',async()=>fixture(async r=>{
 const source=r.overrides[1].source,real=path.join(r.directory,'owned-script.js');
 await writeFile(real,'owned');await rm(source);await symlink(real,source);
 assert.deepEqual(check(r,true),{admitted:false,refusal:'noncanonical-path'});
}));
