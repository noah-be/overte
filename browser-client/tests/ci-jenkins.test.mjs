// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
// The actual native CI owner is Linux-specific. Its complete contract suite is
// included in the existing unit-isolation gate; this adds no weakened/new gate.
test('Jenkins source, ownership, authenticated display and bounded artifact contracts',{
    skip:process.platform!=='linux',timeout:25000,
},async()=>{
    const environment={PYTHONDONTWRITEBYTECODE:'1'};
    for(const key of ['PATH','HOME','LANG','LC_ALL','TZ'])if(process.env[key])environment[key]=process.env[key];
    await promisify(execFile)('python3',[fileURLToPath(new URL('../ci/jenkins/test_runner.py',import.meta.url))],{
        env:environment,timeout:20000,maxBuffer:1024*1024,
    });
});
