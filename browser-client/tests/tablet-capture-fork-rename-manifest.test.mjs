// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Retained V34 CPU assertions; current physical admission is checked by V35.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile as readPhysicalFile, writeFile, mkdtemp, mkdir, rm, unlink, symlink, link, chmod} from 'node:fs/promises';
import {lstat, realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {
    decodeForkRenameHistory, readForkRenameHistory, readForkRenameHistoricalSource,
    normalizeForkRenameInput, recoverCaptureV33Input, readCurrentForkRenameSource,
} from './integration/capture-fork-rename-source-fixture.mjs';

import {recoverCaptureV34Input, readWorkflowHistoricalSource} from './integration/capture-workflow-source-fixture.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const readFile = async (input, options) => {
    const file = input instanceof URL ? fileURLToPath(input) : path.resolve(input);
    const bytes = recoverCaptureV34Input(path.relative(root, file), await readPhysicalFile(input));
    return typeof options === 'string' ? bytes.toString(options) : bytes;
};
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const bytes = await readFile(new URL('./fixtures/capture-fork-rename-v34-complete-source-manifest.json', import.meta.url));
const manifest = JSON.parse(bytes), d = manifest.forkRenameDerivation;
const previousBytes = await readFile(new URL('./fixtures/capture-startup-integration-v33-complete-source-manifest.json', import.meta.url));
const previous = JSON.parse(previousBytes);
const preparerPath = 'browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs';
const preparer = readWorkflowHistoricalSource(preparerPath);
const start = preparer.indexOf('const manifestBytes=await readFile(proposal);');
const end = preparer.indexOf('const directory=await mkdtemp(', start);
assert(start >= 0 && end > start);
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const gate = new AsyncFunction('assert', 'readFile', 'realpath', 'lstat', 'path', 'sha', 'source', 'proposal',
    preparer.slice(start, end) + 'return m;');

async function fixture(fn) {
    const directory = await mkdtemp(path.join(tmpdir(), 'capture-fork-rename-'));
    try {
        for (const name of [...manifest.files.map(row => row.path), '.github/workflows/browser-client.yml', 'browser-client/lab/README.md']) {
            const file = path.join(directory, name);
            await mkdir(path.dirname(file), {recursive: true});
            await writeFile(file, await readFile(path.join(root, name)), {mode: 0o600});
        }
        const proposal = path.join(directory, 'manifest.json');
        await writeFile(proposal, bytes);
        return await fn(path.join(directory, 'browser-client'), proposal, directory);
    } finally { await rm(directory, {recursive: true, force: true}); }
}
const check = (source, proposal) => gate(assert, readFile, realpath, lstat, path, sha, source, proposal);

test('V34 preserves every V33 row and migrates only declared CPU sources and renamed-fork environment pins', async () => {
    assert.equal(manifest.version, 34); assert.equal(previous.version, 33);
    assert.equal(d.previousManifestSHA256, sha(previousBytes));
    assert.equal(previous.files.length, 287); assert.equal(manifest.files.length, 290);
    assert.equal(new Set(manifest.files.map(row => row.path)).size, manifest.files.length);
    assert.deepEqual(Object.keys(d.sourceMigrations).sort(), [
        'browser-client/tests/integration/capture-startup-integration-source-fixture.mjs',
        'browser-client/tests/tablet-capture-startup-integration-manifest.test.mjs',
    ]);
    assert.deepEqual(Object.keys(d.chromeEnvironmentMigrations).sort(), [
        'browser-client/ci/jenkins/README.md', 'browser-client/ci/jenkins/run.py', 'browser-client/ci/jenkins/test_runner.py',
    ]);
    const expected = structuredClone(previous);
    expected.version = 34; expected.scope = manifest.scope; expected.forkRenameDerivation = d;
    for (const row of expected.files) {
        const change = d.sourceMigrations[row.path];
        if (change) Object.assign(row, {beforeSHA256: row.afterSHA256, afterSHA256: change.afterSHA256, bytes: change.bytes});
    }
    for (const name of d.addedRows) {
        assert(!previous.files.some(row => row.path === name));
        const row = manifest.files.find(row => row.path === name);
        assert.equal(row.beforeSHA256, null); expected.files.push(row);
    }
    for (const [name, change] of Object.entries(d.chromeEnvironmentMigrations)) {
        assert.equal(previous.reacquisitionDerivation.chromeEnvironmentSourcePins[name], change.beforeSHA256);
        expected.reacquisitionDerivation.chromeEnvironmentSourcePins[name] = change.afterSHA256;
    }
    assert.deepEqual(manifest, expected);
    for (const row of manifest.files) assert.equal(sha(await readFile(path.join(root, row.path))), row.afterSHA256, row.path);
    assert.equal(d.productionHistoryFallback, false); assert.equal(d.actualRuntimeAcceptance, false);
});

test('current physical fork sources match the exact historical rename and retain strengthened Python guards', async () => {
    const history = readForkRenameHistory();
    assert.equal(history.provenance.renameCommit, '342b202c9976ca602d5d4f1049b44e92aece010c');
    assert.equal(history.provenance.renameParent, 'aa4cbd1fc037f67a69aff56d266242429f65bed5');
    assert.equal(Object.keys(history.files).length, 6);
    assert.equal(d.historyInputCount, 6);
    for (const [name, change] of Object.entries(d.chromeEnvironmentMigrations)) {
        const current = readCurrentForkRenameSource(name, path.join(root, name));
        const before = Buffer.from(readForkRenameHistoricalSource(name));
        assert.equal(sha(before), change.beforeSHA256); assert.equal(sha(current), change.afterSHA256);
        assert.equal(history.provenance.sources[name].blob, change.beforeBlobSHA);
        assert.equal(history.provenance.sources[name].commit, history.provenance.renameParent);
        assert.equal(createHash('sha1').update(`blob ${current.length}\0`).update(current).digest('hex'), change.afterBlobSHA);
        if (!name.endsWith('/test_runner.py')) {
            const oldURL = 'https://github.com/noah-be/overte', newURL = 'https://github.com/noah-l-frank/overte';
            assert.equal(before.toString().split(oldURL).length, 2);
            assert.equal(before.toString().replace(oldURL, newURL), current.toString());
        } else {
            // The renamed-fork regression suite gained a refusal-before-work
            // test; it was not replaced by historical bytes in its real runner.
            assert(current.includes(Buffer.from('test_former_or_foreign_remote_stops_main_before_workspace_and_children')));
            assert(!before.includes(Buffer.from('test_former_or_foreign_remote_stops_main_before_workspace_and_children')));
        }
    }
});

test('retained V33 assertion bodies remain byte-for-byte identical', async () => {
    for (const [name, hash] of Object.entries(d.originalAssertionBodiesSHA256)) {
        const before = readForkRenameHistoricalSource(name), current = await readFile(path.join(root, name), 'utf8');
        const originalBody = before.slice(before.indexOf("test('"));
        assert.equal(current.slice(current.indexOf("test('")), originalBody);
        assert.equal(sha(Buffer.from(originalBody)), hash);
    }
});

test('finite CPU recovery admits both exact versions and rejects unknown or altered history', async () => {
    const history = readForkRenameHistory(); assert(Object.isFrozen(history) && Object.isFrozen(history.files));
    for (const [name, row] of Object.entries(history.files)) {
        assert.equal(sha(Buffer.from(row.source)), row.sha256);
        assert(Object.isFrozen(row));
    }
    for (const name of [...Object.keys(d.chromeEnvironmentMigrations), ...Object.keys(d.sourceMigrations)]) {
        const before = Buffer.from(readForkRenameHistoricalSource(name)), current = await readFile(path.join(root, name));
        assert.deepEqual(recoverCaptureV33Input(name, current), before);
        assert.deepEqual(recoverCaptureV33Input(name, before), before);
        for (const altered of [Buffer.concat([current, Buffer.from('\n')]), Buffer.concat([before, Buffer.from('\n')]), Buffer.from('unknown')]) {
            assert.throws(() => recoverCaptureV33Input(name, altered));
        }
    }
    const archive = await readFile(new URL('./fixtures/capture-v33-fork-rename-before.json.gz', import.meta.url));
    assert.equal(sha(archive), d.historySHA256); assert.equal(archive.length, d.historyGzipBytes);
    assert.equal(gunzipSync(archive, {maxOutputLength: 262144}).length, d.historyInflatedBytes);
    const altered = Buffer.from(archive); altered[altered.length - 1] ^= 1;
    for (const input of [altered, Buffer.concat([archive, Buffer.from('\n')]), Buffer.alloc(131073), new Uint8Array(archive)]) {
        assert.throws(() => decodeForkRenameHistory(input));
    }
    assert.throws(() => readForkRenameHistoricalSource('unknown'));
    assert.throws(() => normalizeForkRenameInput('browser-client/ci/jenkins/run.py', new Uint8Array(0)));
    const untouched = Buffer.from('unowned source');
    assert.equal(normalizeForkRenameInput('unowned', untouched), untouched);
});

test('current physical admission refuses old bytes drift missing files symlinks hardlinks and writable aliases', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'fork-rename-physical-'));
    try {
        for (const name of Object.keys(d.chromeEnvironmentMigrations)) {
            const file = path.join(directory, 'input'), alias = path.join(directory, 'alias');
            const current = await readFile(path.join(root, name)), before = Buffer.from(readForkRenameHistoricalSource(name));
            await writeFile(file, current, {mode: 0o600});
            assert.deepEqual(readCurrentForkRenameSource(name, file), current);
            for (const bad of [before, Buffer.concat([current, Buffer.from('\n')]), Buffer.from('unknown')]) {
                await writeFile(file, bad); assert.throws(() => readCurrentForkRenameSource(name, file));
            }
            await unlink(file); assert.throws(() => readCurrentForkRenameSource(name, file));
            await writeFile(alias, current, {mode: 0o600}); await symlink(alias, file);
            assert.throws(() => readCurrentForkRenameSource(name, file)); await unlink(file);
            await link(alias, file); assert.throws(() => readCurrentForkRenameSource(name, file));
            await unlink(file); await unlink(alias); await writeFile(file, current, {mode: 0o600});
            await chmod(file, 0o622); assert.throws(() => readCurrentForkRenameSource(name, file));
            await unlink(file);
        }
        assert.throws(() => readCurrentForkRenameSource('unknown', path.join(directory, 'missing')));
    } finally { await rm(directory, {recursive: true, force: true}); }
});

test('current V34 shipping gate rejects V33 or invented manifests before reading source', () => fixture(async (source, proposal) => {
    assert.equal((await check(source, proposal)).version, 34);
    for (const wrong of [previousBytes, Buffer.concat([bytes, Buffer.from('\n')]), Buffer.from(JSON.stringify({...manifest, version: 33}))]) {
        await writeFile(proposal, wrong); let reads = 0;
        await assert.rejects(() => gate(assert, async file => { if (file !== proposal) reads++; return readFile(file); },
            realpath, lstat, path, sha, source, proposal));
        assert.equal(reads, 0);
    }
}));

test('current V34 gate rejects altered old missing or symlinked migrated and admitted source rows', () => fixture(async (source, proposal, directory) => {
    for (const name of [...Object.keys(d.sourceMigrations), ...d.addedRows]) {
        const file = path.join(directory, name), current = await readFile(file);
        await writeFile(file, Buffer.concat([current, Buffer.from('\n')])); await assert.rejects(() => check(source, proposal));
        if (Object.hasOwn(d.sourceMigrations, name)) {
            await writeFile(file, readForkRenameHistoricalSource(name)); await assert.rejects(() => check(source, proposal));
        }
        await unlink(file); await assert.rejects(() => check(source, proposal));
        const alias = path.join(directory, 'alias'); await writeFile(alias, current); await symlink(alias, file);
        await assert.rejects(() => check(source, proposal));
        await unlink(file); await unlink(alias); await writeFile(file, current);
    }
}));

test('production preparer changes one manifest digest and never imports historical recovery', () => {
    const before = readForkRenameHistoricalSource(preparerPath);
    assert.equal(preparer.split(sha(bytes)).length, 2);
    assert.equal(preparer.replace(sha(bytes), sha(previousBytes)), before);
    assert(!preparer.includes('source-fixture')); assert(!preparer.includes('recoverCapture'));
    assert(!preparer.includes('normalizeForkRename')); assert(!preparer.includes('readForkRename'));
});
