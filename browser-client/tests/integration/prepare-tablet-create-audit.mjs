// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Prepare a separate, immutable test gateway. Never edit the shipping helper.
import {cp,mkdtemp,readFile,writeFile,symlink,realpath,lstat,mkdir} from 'node:fs/promises';
import path from 'node:path';import {tmpdir} from 'node:os';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';
import {instrumentCreateReadiness} from './tablet-create-readiness.mjs';
const source=await realpath(process.argv[2]||process.cwd());
assert((await lstat(path.join(source,'gateway/server.mjs'))).isFile(),'Supply the reviewed browser-client directory');
const directory=await mkdtemp(path.join(tmpdir(),'overte-create-readiness-gateway-'));await mkdir(path.join(directory,'browser-client'),{mode:0o700});
const client=path.join(directory,'browser-client'),sha=b=>createHash('sha256').update(b).digest('hex');
const qml=await readFile(path.join(source,'gateway/tablet-capture.qml'),'utf8');
await cp(path.join(source,'gateway'),path.join(client,'gateway'),{recursive:true,dereference:false});
await cp(path.join(source,'shared'),path.join(client,'shared'),{recursive:true,dereference:false});
for(const name of ['node_modules','dist','public'])await symlink(path.join(source,name),path.join(client,name),'dir');
const original=await readFile(path.join(client,'gateway/tablet-capture.qml'),'utf8');assert.equal(original,qml,'Shipping QML must stay unchanged during test gateway preparation');
const instrumented=instrumentCreateReadiness(qml);await writeFile(path.join(client,'gateway/tablet-capture.qml'),instrumented,{mode:0o600});
await writeFile(path.join(directory,'audit-manifest.json'),JSON.stringify({version:1,scope:'Read-only native Create readiness audit; shipping helper unchanged',shippingCaptureSHA256:sha(qml),testCaptureSHA256:sha(instrumented)},null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({directory,client,entry:path.join(client,'gateway/server.mjs'),testCaptureSHA256:sha(instrumented)}));
