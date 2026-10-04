// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {cp,mkdtemp,mkdir,readFile,writeFile,symlink,realpath,lstat} from 'node:fs/promises';
import {createHash} from 'node:crypto';import path from 'node:path';import {tmpdir} from 'node:os';import assert from 'node:assert/strict';
import {instrumentEmoteView,instrumentEmoteEvents} from './tablet-sit-audit.mjs';
import {sitCopiedSourceHashes,SIT_COPIED_HELPERS} from './tablet-sit-source.mjs';
import {buildBrowserEmoteOverride} from '../../gateway/tablet-emote.mjs';import {gunzipSync} from 'node:zlib';
const source=await realpath(process.argv[2]||process.cwd());assert((await lstat(path.join(source,'gateway/server.mjs'))).isFile());
const emote=await readFile(path.join(source,'gateway/tablet-emote.mjs'),'utf8');
const marker='const generated=buildBrowserEmoteOverride(await readTrusted(target));';assert.equal(emote.split(marker).length,2,'Integrate the exact reviewed Sit adapter first');
const directory=await mkdtemp(path.join(tmpdir(),'overte-sit-audit-gateway-')),client=path.join(directory,'browser-client');await mkdir(client,{mode:0o700});
for(const name of ['gateway','shared'])await cp(path.join(source,name),path.join(client,name),{recursive:true,dereference:false,preserveTimestamps:true});
for(const name of ['node_modules','dist','public'])await symlink(path.join(source,name),path.join(client,name),'dir');
await mkdir(path.join(client,'tests/integration'),{recursive:true,mode:0o700});for(const name of SIT_COPIED_HELPERS)await cp(new URL('./'+name,import.meta.url),path.join(client,'tests/integration',name));
const shippingSourceSHA256=await sitCopiedSourceHashes(source);
const shipping=await readFile(path.join(source,'gateway/tablet-capture.qml'),'utf8'),capture=instrumentEmoteView(shipping);
const diagnosticEmote="import {instrumentEmoteEvents} from '../tests/integration/tablet-sit-audit.mjs';\n"+emote.replace(marker,'const generated=instrumentEmoteEvents(buildBrowserEmoteOverride(await readTrusted(target)));');
await writeFile(path.join(client,'gateway/tablet-capture.qml'),capture,{mode:0o600});await writeFile(path.join(client,'gateway/tablet-emote.mjs'),diagnosticEmote,{mode:0o600});
const sha=b=>createHash('sha256').update(b).digest('hex');
const original=gunzipSync(await readFile(path.join(source,'gateway/fixtures/native-emote-f91d15a.js.gz')),{maxOutputLength:32768}).toString(),generated=instrumentEmoteEvents(buildBrowserEmoteOverride(original));
const copiedSourceSHA256=await sitCopiedSourceHashes(client);assert.deepEqual(await sitCopiedSourceHashes(source),shippingSourceSHA256,'Root sources must remain unchanged during preparation');
await writeFile(path.join(directory,'audit-manifest.private.json'),JSON.stringify({version:2,shippingSourceSHA256,copiedSourceSHA256,copiedEmoteGeneratedSHA256:sha(generated),shippingCaptureSHA256:sha(shipping),copiedCaptureSHA256:sha(capture),shippingAdapterSHA256:sha(emote),copiedAdapterSHA256:sha(diagnosticEmote),scope:'Fixed read-only original Emote controls and numeric action-return logging. No native command or query endpoint. Original controller/animation calls unchanged.'},null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({directory,client,entry:path.join(client,'gateway/server.mjs'),copiedCaptureSHA256:sha(capture)}));
