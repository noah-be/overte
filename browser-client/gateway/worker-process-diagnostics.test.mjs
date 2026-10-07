// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { workerSurvivorState } from './worker-process-diagnostics.mjs';
test('actual owned process readback exports fixed state, never arguments or identity',async()=>{
    const child=spawn(process.execPath,['-e',"console.log('ready');setInterval(()=>{},1000)",'synthetic-private-argument'],{stdio:['ignore','pipe','ignore']});
    try {
        await once(child.stdout,'data');
        const result=await workerSurvivorState(child.pid);
        assert.match(result.state,/^[RSDZTtXxKWPIN]$/);assert.equal(result.parentIsOwnedPID1,false);
        assert.deepEqual(Object.keys(result),['role','state','parentIsOwnedPID1']);
        assert.equal(JSON.stringify(result).includes('synthetic-private'),false);
    }finally{const exit=once(child,'exit');child.kill('SIGKILL');await exit;}
    assert.equal((await workerSurvivorState(child.pid)).state,'already-reaped');
    await assert.rejects(workerSurvivorState(-1),/Invalid owned descendant PID/);
});
