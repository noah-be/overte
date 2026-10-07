// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Offline diagnostics only; no process, native API, network or browser access.
import { constants } from 'node:fs';
import { open, lstat, realpath } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { EventEmitter } from 'node:events';
import { pathToFileURL } from 'node:url';
import { attachNativeAvatarProjection } from '../gateway/native-avatar-stdout-projection.mjs';

const MARKER = Buffer.from('BROWSER_AVATAR_SAMPLE ');
const MAX_BYTES = 1024 * 1024;
const MAX_ROWS = 512;
const own = value => value.uid === process.getuid() && !(value.mode & 0o022);
const stable = (a, b) => ['dev', 'ino', 'size', 'mtimeMs', 'ctimeMs', 'uid', 'mode', 'nlink'].every(key => a[key] === b[key]);

async function directory(path, privateRoot = false) {
    const metadata = await lstat(path);
    if (!metadata.isDirectory() || !own(metadata) || privateRoot && (metadata.mode & 0o077)
        || await realpath(path) !== resolve(path)) throw new Error('directory-refused');
    return metadata;
}

// Delegate each complete line to the exact production projector. No original
// text, decorators, exceptions or unknown fields can enter the returned DTO.
export function projectAvatarTail(buffer, tailTruncated = false, mode = 'native-child') {
    if (!Buffer.isBuffer(buffer) || buffer.length > MAX_BYTES || typeof tailTruncated !== 'boolean' || !['native-child','gateway-log'].includes(mode)) throw new Error('input-refused');
    const child = new EventEmitter(); child.stdout = new EventEmitter();
    const rows = [];
    attachNativeAvatarProjection(child, { enabled: true, publicPlace: false, mode,
        emit(line) { rows.push(JSON.parse(line.slice(MARKER.length))); } });
    let offset = 0, prefixDiscarded = false;
    if (tailTruncated) {
        const end = buffer.indexOf(10);
        offset = end < 0 ? buffer.length : end + 1;
        prefixDiscarded = buffer.length > 0;
    }
    let markerLines = 0, rejectedMarkerLines = 0, unprocessedCompleteLines = 0;
    let incompleteSuffixDiscarded = false;
    while (offset < buffer.length) {
        const end = buffer.indexOf(10, offset);
        if (end < 0) { incompleteSuffixDiscarded = true; break; }
        const line = buffer.subarray(offset, end + 1);
        if (rows.length >= MAX_ROWS) unprocessedCompleteLines++;
        else {
            const marked = line.includes(MARKER), count = rows.length;
            if (marked) markerLines++;
            child.stdout.emit('data', line);
            if (marked && count === rows.length) rejectedMarkerLines++;
        }
        offset = end + 1;
    }
    child.emit('close');
    return { bytesRead: buffer.length, tailTruncated, prefixDiscarded, incompleteSuffixDiscarded,
        markerLines, rejectedMarkerLines, unprocessedCompleteLines,
        rowBudgetReached: rows.length === MAX_ROWS, rows };
}

export async function readAvatarLog(root, name) {
    if (!['native', 'gateway'].includes(name)) throw new Error('source-refused');
    let handle;
    try {
        const rootBefore = await directory(root, true);
        const logs = join(root, 'logs'), logsBefore = await directory(logs);
        const filename = join(logs, name + '.log'), pathBefore = await lstat(filename);
        if (!pathBefore.isFile() || !own(pathBefore) || pathBefore.nlink !== 1) return { source: name, status: 'refused', reason: 'file-refused' };
        handle = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
        const before = await handle.stat();
        if (!stable(pathBefore, before) || !before.isFile() || !own(before) || before.nlink !== 1
            || !Number.isSafeInteger(before.size) || before.size < 0) return { source: name, status: 'refused', reason: 'file-refused' };
        const start = Math.max(0, before.size - MAX_BYTES), buffer = Buffer.alloc(Math.min(before.size, MAX_BYTES));
        const { bytesRead } = await handle.read(buffer, 0, buffer.length, start);
        const after = await handle.stat(), pathAfter = await lstat(filename);
        if (bytesRead !== buffer.length || !stable(before, after) || !stable(after, pathAfter)
            || !stable(rootBefore, await directory(root, true)) || !stable(logsBefore, await directory(logs))) {
            return { source: name, status: 'refused', reason: 'changed-during-read' };
        }
        return { source: name, status: 'read', ...projectAvatarTail(buffer, start > 0, name==='native'?'native-child':'gateway-log') };
    } catch (error) {
        return { source: name, status: error?.code === 'ENOENT' ? 'missing' : 'refused',
            ...(error?.code === 'ENOENT' ? {} : { reason: 'read-boundary-refused' }) };
    } finally { await handle?.close(); }
}

export async function collectAvatarSamples(root, commitSHA) {
    if (typeof commitSHA !== 'string' || commitSHA.length !== 40 || !/^[0-9a-f]{40}$/.test(commitSHA)) throw new Error('commit-refused');
    const logs = [];
    for (const name of ['native', 'gateway']) logs.push(await readAvatarLog(root, name));
    return { schemaVersion: 1, testedCommitSHA: commitSHA, diagnosticMode: 'full-opt-in',
        status: logs.some(log => log.status === 'refused') ? 'refused' : logs.every(log => log.status === 'missing') ? 'not-observed' : 'projected',
        limits: { bytesPerLog: MAX_BYTES, rowsPerLog: MAX_ROWS, logCount: 2 }, logs,
        interpretation: { acceptance: false, snapshotArrivalIsPoseAge: false, statsFreshnessEstablished: false,
            nativePacketDeliveryEstablished: false, rawLogsIncluded: false } };
}

export async function writeAvatarSamples(filename, report) {
    const parent = resolve(filename, '..');
    const before = await directory(parent);
    let handle;
    try {
        handle = await open(filename, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
        const metadata = await handle.stat(), parentAfter = await directory(parent);
        if (!metadata.isFile() || metadata.uid !== process.getuid() || metadata.nlink !== 1 || (metadata.mode & 0o777) !== 0o600
            || !['dev', 'ino', 'uid', 'mode'].every(key => before[key] === parentAfter[key])) throw new Error('output-refused');
        const data = Buffer.from(JSON.stringify(report) + '\n');
        if (data.length > 1024 * 1024) throw new Error('output-bound-refused');
        await handle.writeFile(data); await handle.sync();
    } finally { await handle?.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
    try {
        const args = process.argv.slice(2);
        if (args.length !== 4 || args[0] !== '--output' || args[2] !== '--commit-sha') throw new Error('arguments-refused');
        const report = await collectAvatarSamples(resolve('build/browser-lab'), args[3]);
        await writeAvatarSamples(resolve(args[1], 'native-avatar-samples.json'), report);
        if (report.status === 'refused') process.exitCode = 1;
    } catch { console.error('Native avatar diagnostic collection refused.'); process.exitCode = 1; }
}
