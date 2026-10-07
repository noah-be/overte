// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {cp,mkdtemp,readFile,writeFile,realpath,lstat,mkdir,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';import path from 'node:path';import {createHash} from 'node:crypto';
import {instrumentGraphicsCapture} from './tablet-graphics-state-audit.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');process.umask(0o077);
const source=await realpath(process.argv[2]||process.cwd());
assert((await lstat(path.join(source,'gateway/server.mjs'))).isFile());
const pins={'gateway/browser-graphics-overrides.mjs':'ccb50787e8bc0431b6c13c67de1ebdbddf9abdc5f7123a64b6b061be89712329','gateway/native-browser-graphics.js':'38b34b386ebb1009654f9c55edd96f95ea24ac052adcdcc9f7c55874f49c31d5','gateway/tablet-capture.qml':'f990c2ed3f5b0d68e50b959774214f4b7637e332b1c9613567c8ea9252f5f1bc','tests/integration/tablet-graphics-scan-session.mjs':'446ce0cc522edeafff54d9ba200096abf21283345744420a942166c3d4525615'};
for(const [f,h]of Object.entries(pins))assert.equal(sha(await readFile(path.join(source,f))),h,'Exact reviewed source before test-only preparation');
const directory=await mkdtemp(path.join(tmpdir(),'overte-graphics-state-gateway-'));await mkdir(path.join(directory,'browser-client'),{mode:0o700});const client=path.join(directory,'browser-client');
await cp(path.join(source,'gateway'),path.join(client,'gateway'),{recursive:true,dereference:false});await cp(path.join(source,'shared'),path.join(client,'shared'),{recursive:true,dereference:false});
for(const name of ['node_modules','dist','public'])await symlink(path.join(source,name),path.join(client,name),'dir');
await mkdir(path.join(client,'tests/integration'),{recursive:true,mode:0o700});
for(const name of ['tablet-create-readiness.mjs'])await cp(path.join(source,'tests/integration',name),path.join(client,'tests/integration',name));
await cp(new URL('./tablet-graphics-state-audit.mjs',import.meta.url),path.join(client,'tests/integration/tablet-graphics-state-audit.mjs'));
const qml=await readFile(path.join(source,'gateway/tablet-capture.qml'),'utf8'),instrumented=instrumentGraphicsCapture(qml);await writeFile(path.join(client,'gateway/tablet-capture.qml'),instrumented,{mode:0o600});
const original=await readFile(path.join(source,'gateway/browser-graphics-overrides.mjs'),'utf8'),anchor="    return {'settings.js':js,'Settings.qml':qml,'qml/pages/GraphicsSettings.qml':graphics,'qml/SettingSlider.qml':sources['qml/SettingSlider.qml'],'qml/SettingBoolean.qml':sources['qml/SettingBoolean.qml'],'qml/SettingComboBox.qml':sources['qml/SettingComboBox.qml']};";
assert.equal(original.split(anchor).length,2);
const altered="import {instrumentGraphicsGenerated} from '../tests/integration/tablet-graphics-state-audit.mjs';\n"+original.replace(anchor,anchor.replace('return {','return instrumentGraphicsGenerated({').replace('};','});'));
await writeFile(path.join(client,'gateway/browser-graphics-overrides.mjs'),altered,{mode:0o600});
const copyHashes={'gateway/tablet-capture.qml':sha(instrumented),'gateway/browser-graphics-overrides.mjs':sha(altered),'tests/integration/tablet-graphics-state-audit.mjs':sha(await readFile(new URL('./tablet-graphics-state-audit.mjs',import.meta.url)))};
await writeFile(path.join(directory,'audit-manifest.private.json'),JSON.stringify({version:1,scope:'Copied-only passive native Graphics state/index trace',sourcePins:pins,copyHashes,shippingControlsUnchanged:true,actualQualification:false},null,2)+'\n',{mode:0o600,flag:'wx'});
console.log(JSON.stringify({directory,client,entry:path.join(client,'gateway/server.mjs'),sourcePins:pins,copyHashes}));
