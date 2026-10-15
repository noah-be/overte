// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Finite CPU history only. Current physical admission never recovers old source.
import {normalizeRetainedWorkflowInput} from './capture-workflow-source-fixture.mjs';
import {openSync, closeSync, fstatSync, readSync, realpathSync, constants} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';

const ARCHIVE = 'b60fee1b16c1226a851e339baaface2b1f36c2396e040131fb8f6e459998733e';
const BEFORE = {"browser-client/ci/jenkins/README.md": "8a6ff009b9a008f8bc0343e04ada491a369fe9c44eb15f47bc0c2bc3d839cc1c", "browser-client/ci/jenkins/run.py": "9b3a43c063a8fb65c39b18636ba6ad79036455f428e595d78f13cfebbded55b7", "browser-client/ci/jenkins/test_runner.py": "be125b173e2f285275050f6a89e15298076ce7bb802e8c693be588345bfe558e", "browser-client/tests/integration/capture-startup-integration-source-fixture.mjs": "bca1bb868167257e97b149de868a27742e0baf1bbe200a7f76e3834d67adc934", "browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs": "55b02bfb628278b0947c2af06c298e6a9688ab3836710244ae57ea8cbbba5c15", "browser-client/tests/tablet-capture-startup-integration-manifest.test.mjs": "64b35fbf6a9028738329bcdd02d3ed28780a90a4989da18d2e9376108ecaef6c"};
const FORK_CURRENT = {"browser-client/ci/jenkins/README.md": "34aeaf89b2512ae1fb42dfca5edb39270406e5aea4010a73b8e279e617f7b542", "browser-client/ci/jenkins/run.py": "990f1b1a755b5bbeb8b4e28e0a5f1e4540800c35b0d3520b2123605409133241", "browser-client/ci/jenkins/test_runner.py": "944dbdd291dd186c21d2062e33839449fb89ad467103345fede94e3dfbeb7254"};
const CPU_CURRENT = {"browser-client/tests/integration/capture-startup-integration-source-fixture.mjs": "ef2002e796bb3e99cb4ae01d4823e5ff8ffbfc065ae060da4b787f2029405ee6", "browser-client/tests/tablet-capture-startup-integration-manifest.test.mjs": "170b5c54e730334e8d090406ca04d12183e60a4b3efdc8ee01c4ecc2486f7516"};
const BASE = '2750afb6416a4dc71366974f24c8e3e87e5228af';
const RENAME = '342b202c9976ca602d5d4f1049b44e92aece010c';
const PARENT = 'aa4cbd1fc037f67a69aff56d266242429f65bed5';
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const blobDigest = bytes => createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
const refuse = () => { throw Error('Historical fork rename source refused'); };

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

export function decodeForkRenameHistory(bytes) {
    if (!Buffer.isBuffer(bytes) || bytes.length < 1 || bytes.length > 131072 || digest(bytes) !== ARCHIVE) refuse();
    const value = JSON.parse(gunzipSync(bytes, {maxOutputLength: 262144}));
    if (value?.version !== 1 || Object.keys(value).sort().join(',') !== 'files,provenance,version'
        || Object.keys(value.files || {}).sort().join(',') !== Object.keys(BEFORE).sort().join(',')) refuse();
    const p = value.provenance;
    if (!p || Object.keys(p).sort().join(',') !== 'baseCommit,renameCommit,renameParent,sources'
        || p.baseCommit !== BASE || p.renameCommit !== RENAME || p.renameParent !== PARENT
        || Object.keys(p.sources || {}).sort().join(',') !== Object.keys(BEFORE).sort().join(',')) refuse();
    for (const [name, hash] of Object.entries(BEFORE)) {
        const row = value.files[name], source = p.sources[name];
        if (!row || Object.keys(row).sort().join(',') !== 'sha256,source'
            || row.sha256 !== hash || typeof row.source !== 'string' || digest(Buffer.from(row.source)) !== hash
            || !source || Object.keys(source).sort().join(',') !== 'blob,commit'
            || source.commit !== (Object.hasOwn(FORK_CURRENT, name) ? PARENT : BASE)
            || source.blob !== blobDigest(Buffer.from(row.source))) refuse();
        Object.freeze(row); Object.freeze(source);
    }
    Object.freeze(p.sources); Object.freeze(p); Object.freeze(value.files);
    return Object.freeze(value);
}

let history;
export function readForkRenameHistory() {
    if (!history) history = decodeForkRenameHistory(readHeldFile(fileURLToPath(
        new URL('../fixtures/capture-v33-fork-rename-before.json.gz', import.meta.url)), 131072));
    return history;
}

export function readForkRenameHistoricalSource(relative) {
    if (!Object.hasOwn(BEFORE, relative)) refuse();
    return readForkRenameHistory().files[relative].source;
}

function recover(relative, bytes, current) {
    if (!Buffer.isBuffer(bytes)) refuse();
    if (!Object.hasOwn(current, relative)) return bytes;
    const hash = digest(bytes);
    if (hash === BEFORE[relative]) return bytes;
    if (hash !== current[relative]) refuse();
    return Buffer.from(readForkRenameHistoricalSource(relative));
}

export function normalizeForkRenameInput(relative, bytes) {
    return recover(relative, normalizeRetainedWorkflowInput(relative, bytes), FORK_CURRENT);
}

export function recoverCaptureV33Input(relative, bytes) {
    return recover(relative, normalizeForkRenameInput(relative, bytes), CPU_CURRENT);
}

export function readCurrentForkRenameSource(relative, file) {
    if (!Object.hasOwn(FORK_CURRENT, relative)) refuse();
    const bytes = readHeldFile(file, 65536);
    if (digest(bytes) !== FORK_CURRENT[relative]) refuse();
    return bytes;
}
