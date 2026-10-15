// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Finite V34 workflow history only. Physical admission requires the exact canonical generation.
import {openSync, closeSync, fstatSync, readSync, realpathSync, constants} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';

const ARCHIVE = "38296e4fed3e546631e1690bb6e488bf37a596b06657f6a59b4803db767b303a";
const BEFORE = {".github/workflows/browser-client.yml": "5ef53a7c48d502b8c64d0d22042a50a5ac37c15c35b55fde9149deaa2e768a20", "browser-client/tests/integration/capture-fork-rename-source-fixture.mjs": "132980dd3fb3db905a257adc1beb1cabc65a2f5cdf136c472aac2dcac72c47c0", "browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs": "96aaa40880dfed65bd4361ce8555ba06e902bcb970ad7e1a036aa88a529526de", "browser-client/tests/tablet-capture-fork-rename-manifest.test.mjs": "138a9088f0e2a8e20cbf9a5f831a4f0cb71c77508bdc1373fc137626e7165e39", "browser-client/tests/embedded-world-software-ci.test.mjs": "721087f99954e684204025eb53e822930e9b05af9745d543555b3883a7281d94"};
const WORKFLOW_CURRENT = {".github/workflows/browser-client.yml": "74c4ab6d18a40d910e6306c281db2c07fb0f08aa012f2001acce6436d221e417"};
const CPU_CURRENT = {"browser-client/tests/integration/capture-fork-rename-source-fixture.mjs": "8ec9ae03e25a7a8e17bc1f2dd6fb475498c2c44a79e4a3413316460964b2ed4b", "browser-client/tests/tablet-capture-fork-rename-manifest.test.mjs": "7c447dced06da00ae856b6aa1dacb93617b2ac88449d1e8108b26558beaeecba", "browser-client/tests/embedded-world-software-ci.test.mjs": "3776e9f14e32c3f4a02b0fd30327fc88dbe597556cf739a0a8e544f4ffa1d938"};
const BASE = "1a87371f7644e88bc2609b4b5830c6f1ae64594d";
const TEMPLATE = "e4ce7d451bc8523ef4cc8bc29cd2e8e17aec989a";
const TEMPLATE_BLOB = "ed61f454f9048d9532b162e8ee716decd2a6b776";
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const blobDigest = bytes => createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
const refuse = () => { throw Error('Historical workflow transition source refused'); };

function readHeldFile(file, maximum) {
    if (typeof file !== 'string' || path.resolve(file) !== file || realpathSync(file) !== file) refuse();
    const fd = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    try {
        const before = fstatSync(fd);
        if (!before.isFile() || before.uid !== process.getuid() || before.nlink !== 1
            || (before.mode & 0o022) || before.size < 1 || before.size > maximum) refuse();
        const bytes = Buffer.alloc(maximum + 1);
        let count = 0;
        while (count < bytes.length) {
            const n = readSync(fd, bytes, count, bytes.length - count, count);
            if (!n) break;
            count += n;
        }
        const after = fstatSync(fd);
        if (count !== before.size || count > maximum
            || !['dev', 'ino', 'size', 'uid', 'mode', 'nlink', 'mtimeMs', 'ctimeMs'].every(key => before[key] === after[key])) refuse();
        return bytes.subarray(0, count);
    } finally { closeSync(fd); }
}

export function decodeWorkflowHistory(bytes) {
    if (!Buffer.isBuffer(bytes) || bytes.length < 1 || bytes.length > 131072 || digest(bytes) !== ARCHIVE) refuse();
    const value = JSON.parse(gunzipSync(bytes, {maxOutputLength: 262144}));
    if (value?.version !== 1 || Object.keys(value).sort().join(',') !== 'files,provenance,version'
        || Object.keys(value.files || {}).sort().join(',') !== Object.keys(BEFORE).sort().join(',')) refuse();
    const p = value.provenance;
    if (!p || Object.keys(p).sort().join(',') !== 'baseCommit,sources,templateBlob,templateCommit'
        || p.baseCommit !== BASE || p.templateCommit !== TEMPLATE || p.templateBlob !== TEMPLATE_BLOB
        || Object.keys(p.sources || {}).sort().join(',') !== Object.keys(BEFORE).sort().join(',')) refuse();
    for (const [name, hash] of Object.entries(BEFORE)) {
        const row = value.files[name], source = p.sources[name];
        if (!row || Object.keys(row).sort().join(',') !== 'sha256,source'
            || row.sha256 !== hash || typeof row.source !== 'string' || digest(Buffer.from(row.source)) !== hash
            || !source || Object.keys(source).sort().join(',') !== 'blob,commit'
            || source.commit !== BASE
            || source.blob !== blobDigest(Buffer.from(row.source))) refuse();
        Object.freeze(row); Object.freeze(source);
    }
    Object.freeze(p.sources); Object.freeze(p); Object.freeze(value.files);
    return Object.freeze(value);
}

let history;
export function readWorkflowHistory() {
    if (!history) history = decodeWorkflowHistory(readHeldFile(fileURLToPath(
        new URL('../fixtures/capture-v34-workflow-before.json.gz', import.meta.url)), 131072));
    return history;
}

export function readWorkflowHistoricalSource(relative) {
    if (!Object.hasOwn(BEFORE, relative)) refuse();
    return readWorkflowHistory().files[relative].source;
}

function recover(relative, bytes, current) {
    if (!Buffer.isBuffer(bytes)) refuse();
    if (!Object.hasOwn(current, relative)) return bytes;
    const hash = digest(bytes);
    if (hash === BEFORE[relative]) return bytes;
    if (hash !== current[relative]) refuse();
    return Buffer.from(readWorkflowHistoricalSource(relative));
}

export function normalizeWorkflowInput(relative, bytes) {
    return recover(relative, bytes, WORKFLOW_CURRENT);
}

export function normalizeRetainedWorkflowInput(relative, bytes) {
    // V25/V26 already test this exact V26 before-image through the successor
    // chain. Retain it unchanged for its original strict owner; do not recover
    // it into V34 or admit it as current physical workflow source.
    if (Buffer.isBuffer(bytes) && relative === '.github/workflows/browser-client.yml'
        && digest(bytes) === 'd608f4173399093959bda9362953a46589d02b08893cc5468c0c09c0de358202') return bytes;
    return recoverCaptureV34Input(relative, bytes);
}

export function recoverCaptureV34Input(relative, bytes) {
    return recover(relative, normalizeWorkflowInput(relative, bytes), CPU_CURRENT);
}

export function readCurrentWorkflowSource(relative, file) {
    if (!Object.hasOwn(WORKFLOW_CURRENT, relative)) refuse();
    const bytes = readHeldFile(file, 65536);
    if (digest(bytes) !== WORKFLOW_CURRENT[relative]) refuse();
    return bytes;
}
