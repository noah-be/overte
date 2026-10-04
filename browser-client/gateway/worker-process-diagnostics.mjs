// SPDX-License-Identifier: Apache-2.0
import { open } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const ownedInit = fileURLToPath(new URL('../ci/jenkins/namespace-owner.py', import.meta.url));
async function boundedRead(filename, limit) {
    const descriptor = await open(filename, 'r');
    try {
        const bytes = Buffer.alloc(limit + 1);
        const { bytesRead } = await descriptor.read(bytes, 0, bytes.length, 0);
        if (bytesRead > limit) throw Error('Owned process diagnostic exceeds bound');
        return bytes.subarray(0, bytesRead).toString('utf8');
    } finally { await descriptor.close(); }
}
/** Fixed enums only; never proc command names, arguments, PIDs or paths. */
export async function workerSurvivorState(pid) {
    if (!Number.isSafeInteger(pid) || pid <= 0) throw Error('Invalid owned descendant PID');
    try {
        const stat = await boundedRead(`/proc/${pid}/stat`, 2048);
        const delimiter = stat.lastIndexOf(') ');
        if (delimiter < 0) throw Error('Malformed owned process stat');
        const fields = stat.slice(delimiter + 2).trim().split(/\s+/);
        const state = /^[RSDZTtXxKWPIN]$/.test(fields[0]) ? fields[0] : 'unknown';
        let parentIsOwnedPID1 = false;
        if (fields[1] === '1') {
            const initArguments = (await boundedRead('/proc/1/cmdline', 8192)).split('\0');
            parentIsOwnedPID1 = initArguments.includes(ownedInit);
        }
        return { role: 'owned-worker-descendant', state, parentIsOwnedPID1 };
    } catch (error) {
        return { role: 'owned-worker-descendant', state: error.code === 'ENOENT' ? 'already-reaped' : 'unknown', parentIsOwnedPID1: null };
    }
}
