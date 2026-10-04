// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Creates an independently owned source tree; never writes a linked production tree.
import {cp,mkdtemp,readFile,writeFile,symlink,realpath,lstat,mkdir} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';import {createHash} from 'node:crypto';import path from 'node:path';import {tmpdir} from 'node:os';import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {instrumentPttAudit} from './tablet-ptt-audit.mjs';
const source=await realpath(process.argv[2]||process.cwd()),ptt=await realpath(process.argv[3]),followup=await realpath(process.argv[4]);
assert((await lstat(path.join(source,'gateway/server.mjs'))).isFile());
const directory=await mkdtemp(path.join(tmpdir(),'overte-ptt-acceptance-')),client=path.join(directory,'browser-client');await mkdir(client,{mode:0o700});
for(const name of ['gateway','shared','src','tools','public','tests'])await cp(path.join(source,name),path.join(client,name),{recursive:true,dereference:true});
await mkdir(path.join(client,'lab'),{mode:0o700});
for(const name of ['native-admin.mjs','native-admin.d.mts'])await cp(path.join(source,'lab',name),path.join(client,'lab',name));
for(const name of ['package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html'])await cp(path.join(source,name),path.join(client,name));
await symlink(path.join(source,'node_modules'),path.join(client,'node_modules'),'dir');
for(const name of ['LICENSE','LICENSES/Apache-2.0.txt','interface/resources/meshes/defaultAvatar_full.fst','interface/resources/meshes/mannequin/mannequin.fbx','interface/resources/meshes/mannequin/lambert1_Base_Color.png','interface/resources/meshes/mannequin/lambert1_Normal_OpenGL.png','interface/resources/meshes/mannequin/lambert1_Roughness.png','interface/resources/meshes/mannequin/Eyes.png']){const output=path.join(directory,name);await mkdir(path.dirname(output),{recursive:true});await cp(path.join(source,'..',name),output);}
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const patches=[path.join(ptt,'push-to-talk-final-current.patch'),path.join(followup,'ordinary-mute-held-intent.patch')];
const expectedPatches=['40fcb2db8a00291217e1a030aeabc4a233eeb5903fe4c56cb7914f7c10927abf','1e58e61c1e7687a67b71c3e5c2cff06d9bf07fe6435cd3f1943124294c9269b2'];
for(const [index,patch] of patches.entries()){
 assert.equal(sha(await readFile(patch)),expectedPatches[index],'Only the exact reviewed immutable PTT proposals are admitted');
 // Fuzz-free contextual composition: unknown current source refuses rather than
 // overwriting a newer gateway or bypassing any admission/ownership gate.
 const check=spawnSync('/usr/bin/patch',['--dry-run','--batch','--forward','--fuzz=0','-p1','-i',patch],{cwd:directory,stdio:'ignore',timeout:10000});assert.equal(check.status,0,'PTT source composition refused');
 const apply=spawnSync('/usr/bin/patch',['--batch','--forward','--fuzz=0','-p1','-i',patch],{cwd:directory,stdio:'ignore',timeout:10000});assert.equal(apply.status,0,'PTT source composition failed');
}
for(const name of ['tablet-ptt-audit.mjs','tablet-push-to-talk.mjs'])await cp(path.join(path.dirname(fileURLToPath(import.meta.url)),name),path.join(client,'tests/integration',name));
const qml=await readFile(path.join(client,'gateway/tablet-capture.qml'),'utf8'),audit=instrumentPttAudit(qml);await writeFile(path.join(client,'gateway/tablet-capture.qml'),audit,{mode:0o600});
const manifest={version:1,scope:'Copied private source, reviewed PTT patches, fixed passive native Audio geometry/state; no shipping source writes or setters',shippingCaptureSHA256:sha(qml),auditCaptureSHA256:sha(audit),patchSHA256:await Promise.all(patches.map(async file=>sha(await readFile(file))))};
await writeFile(path.join(directory,'audit-manifest.json'),JSON.stringify(manifest,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({directory,client,entry:path.join(client,'gateway/server.mjs'),auditCaptureSHA256:manifest.auditCaptureSHA256}));
