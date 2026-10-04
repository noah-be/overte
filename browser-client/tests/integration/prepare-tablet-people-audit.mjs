// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {cp,mkdtemp,readFile,writeFile,symlink,realpath,lstat,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';import path from 'node:path';import {tmpdir} from 'node:os';import assert from 'node:assert/strict';
import {instrumentPeopleAudit} from './tablet-people-audit.mjs';
const source=await realpath(process.argv[2]||process.cwd());assert((await lstat(path.join(source,'gateway/server.mjs'))).isFile());
const directory=await mkdtemp(path.join(tmpdir(),'overte-people-audit-gateway-')),client=path.join(directory,'browser-client');await mkdir(client,{mode:0o700});
const qml=await readFile(path.join(source,'gateway/tablet-capture.qml'),'utf8');
await cp(path.join(source,'gateway'),path.join(client,'gateway'),{recursive:true,dereference:false});await cp(path.join(source,'shared'),path.join(client,'shared'),{recursive:true,dereference:false});
for(const name of ['node_modules','dist','public'])await symlink(path.join(source,name),path.join(client,name),'dir');
assert.equal(await readFile(path.join(client,'gateway/tablet-capture.qml'),'utf8'),qml);const copied=instrumentPeopleAudit(qml);await writeFile(path.join(client,'gateway/tablet-capture.qml'),copied,{mode:0o600});
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');await writeFile(path.join(directory,'audit-manifest.json'),JSON.stringify({version:1,shippingCaptureSHA256:sha(qml),testCaptureSHA256:sha(copied),scope:'Fixed passive People geometry/status only. No native setters or incoming query command.'},null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({directory,client,entry:path.join(client,'gateway/server.mjs'),testCaptureSHA256:sha(copied)}));
