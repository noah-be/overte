// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact whole-source CPU history for both merge parents; never a shipping fallback.
import {openSync, closeSync, fstatSync, readSync, realpathSync, constants} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';

const ARCHIVE = '2b8d7eb9b8a8283c558d58e74a5fa78b5e1c0d5094bd3b3027ef13835a84d9ac';
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const refuse = () => { throw Error('Historical startup integration source refused'); };
const hashPattern = /^[0-9a-f]{64}$/;

export function decodeStartupIntegrationHistory(bytes) {
    if (!Buffer.isBuffer(bytes) || bytes.length < 1 || bytes.length > 262144 || digest(bytes) !== ARCHIVE) refuse();
    const value = JSON.parse(gunzipSync(bytes, {maxOutputLength: 2097152}));
    if (value?.version !== 1 || Object.keys(value).sort().join(',') !== 'profiles,version'
        || Object.keys(value.profiles || {}).sort().join(',') !== 'movement,startup') refuse();
    for (const profile of Object.values(value.profiles)) {
        if (Object.keys(profile).sort().join(',') !== 'current,files,historical') refuse();
        for (const [name, row] of Object.entries(profile.files)) {
            if (!name.startsWith('browser-client/') || name.includes('..')
                || Object.keys(row).sort().join(',') !== 'sha256,source'
                || typeof row.source !== 'string' || !hashPattern.test(row.sha256)
                || digest(Buffer.from(row.source)) !== row.sha256) refuse();
            Object.freeze(row);
        }
        for (const [name, hash] of Object.entries(profile.current)) {
            if (!Object.hasOwn(profile.files, name) || !hashPattern.test(hash)
                || !Array.isArray(profile.historical[name])
                || !profile.historical[name].every(item => typeof item === 'string' && hashPattern.test(item))) refuse();
            Object.freeze(profile.historical[name]);
        }
        Object.freeze(profile.files); Object.freeze(profile.current); Object.freeze(profile.historical); Object.freeze(profile);
    }
    Object.freeze(value.profiles);
    return Object.freeze(value);
}

function loadHistory() {
    const file = fileURLToPath(new URL('../fixtures/capture-startup-integration-parents.json.gz', import.meta.url));
    if (realpathSync(file) !== file) refuse();
    const fd = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    try {
        const before = fstatSync(fd);
        if (!before.isFile() || before.uid !== process.getuid() || before.nlink !== 1
            || (before.mode & 0o022) || before.size < 1 || before.size > 262144) refuse();
        const bytes = Buffer.alloc(262145);
        let count = 0;
        while (count < bytes.length) {
            const read = readSync(fd, bytes, count, bytes.length - count, count);
            if (!read) break;
            count += read;
        }
        const after = fstatSync(fd);
        if (count !== before.size || count > 262144
            || !['dev', 'ino', 'size', 'uid', 'mode', 'nlink', 'mtimeMs', 'ctimeMs'].every(key => before[key] === after[key])) refuse();
        return decodeStartupIntegrationHistory(bytes.subarray(0, count));
    } finally { closeSync(fd); }
}

const history = loadHistory();

export function readStartupIntegrationParentSource(profile, relative) {
    if (!Object.hasOwn(history.profiles, profile) || !Object.hasOwn(history.profiles[profile].files, relative)) refuse();
    return history.profiles[profile].files[relative].source;
}

export function normalizeStartupIntegrationInput(profile, relative, bytes) {
    if (!Object.hasOwn(history.profiles, profile) || !Buffer.isBuffer(bytes)) refuse();
    const entry = history.profiles[profile];
    if (!Object.hasOwn(entry.current, relative)) return bytes;
    const hash = digest(bytes);
    if (hash === entry.current[relative]) return Buffer.from(entry.files[relative].source);
    if (hash === entry.files[relative].sha256 || entry.historical[relative].includes(hash)) return bytes;
    refuse();
}
