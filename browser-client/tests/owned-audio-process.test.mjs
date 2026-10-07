// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {ownedAudioProcess} from './integration/owned-audio-process.mjs';

const node=(source,options)=>ownedAudioProcess(process.execPath,['-e',source],options);
test('real early child exit remains observable after delayed capture awaits',async()=>{
    const process=node('process.exit(0)');
    const settled=await process.completion;
    assert.equal(settled.kind,'exited');assert.equal(settled.exitCode,0);
    await delay(30);
    assert.equal(await process.completion,settled);
    assert.equal(await process.stop(),settled);
});
test('spawn failure is owned immediately and has no unhandled promise rejection',async()=>{
    const process=ownedAudioProcess('/this-reviewed-test-command-does-not-exist',[]);
    await delay(30);
    const result=await process.completion;
    assert.equal(result.kind,'spawn-error');assert.equal(result.errorCode,'ENOENT');
});
test('real deadline stops a child which ignores TERM using bounded KILL escalation',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-audio-deadline-'));
    const ready=path.join(directory,'ready'),start=Date.now();
    // Parallel suites can delay the Node bootstrap beyond 200ms. Require an
    // actual installed TERM handler before evaluating escalation, while the
    // total launch/deadline/reaping bound remains below the original 2 seconds.
    const source="process.on('SIGTERM',()=>{});require('node:fs').writeFileSync("+JSON.stringify(ready)+",'armed');setInterval(()=>{},1000)";
    const process=node(source,{timeoutMs:1000,graceMs:30});
    try {
        let armed=false;
        while(Date.now()-start<800){
            try{armed=(await readFile(ready,'utf8'))==='armed';}catch(error){if(error.code!=='ENOENT')throw error;}
            if(armed)break;
            await delay(10);
        }
        assert.equal(armed,true,'The actual child must register its TERM handler before the deadline');
        const result=await process.completion;
        assert.equal(result.kind,'deadline');assert.equal(result.signal,'SIGKILL');
        assert.ok(Date.now()-start>=1000);assert.ok(Date.now()-start<2000);
    } finally {await process.stop();await rm(directory,{recursive:true,force:true});}
});
test('capture failure cleanup is shared, idempotent and does not leave the owned child alive',async()=>{
    const process=node('setInterval(()=>{},1000)',{timeoutMs:5000,graceMs:30});
    await delay(50);
    const first=process.stop(),second=process.stop();assert.equal(first,second);
    const result=await first;
    assert.equal(result.kind,'stopped');assert.ok(['SIGTERM','SIGKILL'].includes(result.signal));
    assert.equal(await process.stop(),result);
    assert.throws(()=>process.kill('SIGTERM')); // No raw mutable child is exported.
});
test('reader abort revokes owned work, while an already-aborted reader never spawns',async()=>{
    const controller=new AbortController();controller.abort();
    const skipped=node('process.exit(1)',{signal:controller.signal});
    assert.equal(skipped.pid,undefined);assert.equal((await skipped.completion).kind,'aborted');
    const next=new AbortController();const process=node('setInterval(()=>{},1000)',{signal:next.signal,graceMs:30});
    next.abort();assert.equal((await process.completion).kind,'aborted');
});
test('invalid resource bounds cannot spawn work',()=>{
    for(const options of [{timeoutMs:0},{timeoutMs:30001},{graceMs:0},{graceMs:2001}]) {
        assert.throws(()=>node('process.exit(0)',options),/bounds/);
    }
});
