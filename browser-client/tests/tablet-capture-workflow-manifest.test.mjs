// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Current physical V35 admission; earlier CPU assertions retain their exact history.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdtemp, mkdir, rm, unlink, symlink, link, chmod, lstat, realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import vm from 'node:vm';
import {
    decodeWorkflowHistory, readWorkflowHistory, readWorkflowHistoricalSource,
    normalizeWorkflowInput, normalizeRetainedWorkflowInput, recoverCaptureV34Input, readCurrentWorkflowSource,
} from './integration/capture-workflow-source-fixture.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const blob = bytes => createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
const bytes = await readFile(new URL('./fixtures/capture-workflow-v35-complete-source-manifest.json', import.meta.url));
const manifest = JSON.parse(bytes), d = manifest.workflowDerivation;
const previousBytes = await readFile(new URL('./fixtures/capture-fork-rename-v34-complete-source-manifest.json', import.meta.url));
const previous = JSON.parse(previousBytes);
const workflowPath = '.github/workflows/browser-client.yml';
const preparerPath = 'browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs';
const preparer = await readFile(path.join(root, preparerPath), 'utf8');
const start = preparer.indexOf('const manifestBytes=await readFile(proposal);');
const end = preparer.indexOf('const directory=await mkdtemp(', start);
assert(start >= 0 && end > start);
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const gate = new AsyncFunction('assert', 'readFile', 'realpath', 'lstat', 'path', 'sha', 'source', 'proposal',
    preparer.slice(start, end) + 'return m;');

async function fixture(fn) {
    const directory = await mkdtemp(path.join(tmpdir(), 'capture-workflow-'));
    try {
        for (const name of [...manifest.files.map(row => row.path), workflowPath, 'browser-client/lab/README.md']) {
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

test('V35 preserves every V34 row with exactly three CPU migrations three admissions and one workflow pin migration', async () => {
    assert.equal(manifest.version, 35); assert.equal(previous.version, 34);
    assert.equal(d.previousManifestSHA256, sha(previousBytes));
    assert.equal(previous.files.length, 290); assert.equal(manifest.files.length, 293);
    assert.equal(new Set(manifest.files.map(row => row.path)).size, manifest.files.length);
    assert.deepEqual(Object.keys(d.sourceMigrations).sort(), [
        'browser-client/tests/embedded-world-software-ci.test.mjs',
        'browser-client/tests/integration/capture-fork-rename-source-fixture.mjs',
        'browser-client/tests/tablet-capture-fork-rename-manifest.test.mjs',
    ]);
    assert.deepEqual(d.addedRows, [
        'browser-client/tests/integration/capture-workflow-source-fixture.mjs',
        'browser-client/tests/fixtures/capture-v34-workflow-before.json.gz',
        'browser-client/tests/tablet-capture-workflow-manifest.test.mjs',
    ]);
    const expected = structuredClone(previous);
    expected.version = 35; expected.scope = manifest.scope; expected.workflowDerivation = d;
    for (const row of expected.files) {
        const change = d.sourceMigrations[row.path];
        if (change) Object.assign(row, {beforeSHA256: row.afterSHA256, afterSHA256: change.afterSHA256, bytes: change.bytes});
    }
    for (const name of d.addedRows) {
        assert(!previous.files.some(row => row.path === name));
        const row = manifest.files.find(row => row.path === name);
        assert.equal(row.beforeSHA256, null); expected.files.push(row);
    }
    assert.equal(previous.reacquisitionDerivation.chromeEnvironmentSourcePins[workflowPath], d.workflowMigration.beforeSHA256);
    expected.reacquisitionDerivation.chromeEnvironmentSourcePins[workflowPath] = d.workflowMigration.afterSHA256;
    assert.deepEqual(manifest, expected);
    for (const row of manifest.files) assert.equal(sha(await readFile(path.join(root, row.path))), row.afterSHA256, row.path);
    assert.equal(d.productionHistoryFallback, false); assert.equal(d.actualRuntimeAcceptance, false);
    assert.equal(d.browserJourneyAssertionsChanged, false);
});

test('workflow admission binds the exact old Git source and the exact reviewed canonical generation', async () => {
    const history = readWorkflowHistory(), migration = d.workflowMigration;
    assert.equal(history.provenance.baseCommit, '1a87371f7644e88bc2609b4b5830c6f1ae64594d');
    assert.equal(history.provenance.templateCommit, 'e4ce7d451bc8523ef4cc8bc29cd2e8e17aec989a');
    assert.equal(history.provenance.templateBlob, 'ed61f454f9048d9532b162e8ee716decd2a6b776');
    assert.equal(Object.keys(history.files).length, 5); assert.equal(d.historyInputCount, 5);
    const before = Buffer.from(readWorkflowHistoricalSource(workflowPath));
    const current = readCurrentWorkflowSource(workflowPath, path.join(root, workflowPath));
    const canonical = await readFile(path.join(root, 'tools/repository-checks/workflows/browser-client.yml'));
    assert.equal(sha(before), '5ef53a7c48d502b8c64d0d22042a50a5ac37c15c35b55fde9149deaa2e768a20');
    assert.equal(sha(current), '74c4ab6d18a40d910e6306c281db2c07fb0f08aa012f2001acce6436d221e417');
    assert.deepEqual(current, canonical);
    assert.equal(blob(before), migration.beforeBlobSHA);
    assert.equal(history.provenance.sources[workflowPath].blob, migration.beforeBlobSHA);
    assert.equal(blob(current), migration.afterBlobSHA);
    assert.equal(migration.afterBlobSHA, history.provenance.templateBlob);
    assert.equal(migration.afterSHA256, sha(current)); assert.equal(migration.bytes, current.length);
});

test('physical current software ANGLE diagnostics and all retained browser and native steps remain exact', async () => {
    const current = readCurrentWorkflowSource(workflowPath, path.join(root, workflowPath)).toString();
    const before = readWorkflowHistoricalSource(workflowPath);
    const jobs = 'jobs:\n', browser = '  browser:\n', verify = '\n  verify:\n';
    assert.equal(current.split(jobs).length, 2); assert.equal(current.split(browser).length, 2);
    assert.equal(current.split(verify).length, 2);
    let recovered = current.slice(0, current.indexOf(jobs) + jobs.length)
        + current.slice(current.indexOf(browser), current.indexOf(verify));
    const selection = "    needs: route\n    if: needs.route.outputs.mode == 'full'\n";
    assert.equal(recovered.split(selection).length, 3);
    recovered = recovered.split(selection).join('');
    const audit = "      - name: Audit changed browser package inputs\n        if: needs.route.outputs.audit == 'true'\n        run: npm audit --audit-level=high\n";
    assert.equal(recovered.split(audit).length, 2); recovered = recovered.replace(audit, '');
    // Only the exact reviewed route/CPU/verify jobs, two selection guards and
    // the single audit step are removed. Every original byte must remain.
    assert.equal(recovered, before);
    const input = "      embedded_default_angle_control:\n        description: 'Run the unchanged embedded GPU proof with the original default ANGLE selection instead of the software-fixture driver request'\n        type: boolean\n        default: false\n";
    assert.equal(current.split(input).length, 2);
    assert(!current.includes('embedded_swangle_diagnostic'));
    const expressions = [...current.matchAll(/OVERTE_EMBEDDED_USE_SWANGLE: \$\{\{ ([^\n]+) \}\}/g)];
    assert.equal(expressions.length, 1);
    for (const [event, control, expected] of [
        ['pull_request', false, '1'], ['pull_request', true, '1'], ['push', true, '1'],
        ['workflow_dispatch', false, '1'], ['workflow_dispatch', undefined, '1'], ['workflow_dispatch', true, '0'],
    ]) {
        assert.equal(vm.runInNewContext(expressions[0][1], {
            github: {event_name: event}, inputs: {embedded_default_angle_control: control},
        }), expected);
    }
    assert.equal(sha(await readFile(path.join(root, 'browser-client/tests/integration/embedded-world.mjs'))),
        'dd7325199f929f82143252d0444e9860a2c3728d4a330501e2ba36fcbe443044');
});

test('all retained capture fixtures and V5 through V34 assertion bodies remain immutable', async () => {
    assert.equal(sha(previousBytes), 'f5b6995554b711be7e23170bf159bea8143781e8f86b5b2b39b2aa35b33a1990');
    const versions = new Set();
    for (const [name, hash] of Object.entries(d.historicalFixturesSHA256)) {
        const source = await readFile(path.join(root, name));
        assert.equal(sha(source), hash, name);
        if (name.endsWith('-complete-source-manifest.json')) versions.add(JSON.parse(source).version);
    }
    assert.deepEqual([...versions].sort((a, b) => a - b), Array.from({length: 30}, (_, index) => index + 5));
    for (const [name, hash] of Object.entries(d.originalAssertionBodiesSHA256)) {
        const current = await readFile(path.join(root, name), 'utf8');
        const start = current.indexOf('test('); assert(start >= 0, name);
        assert.equal(sha(Buffer.from(current.slice(start))), hash, name);
    }
    const name = 'browser-client/tests/tablet-capture-fork-rename-manifest.test.mjs';
    const before = readWorkflowHistoricalSource(name), current = await readFile(path.join(root, name), 'utf8');
    assert.equal(current.slice(current.indexOf('test(')), before.slice(before.indexOf('test(')));
});

test('finite workflow CPU history accepts only exact declared versions and refuses altered archives or sources', async () => {
    const history = readWorkflowHistory(); assert(Object.isFrozen(history) && Object.isFrozen(history.files));
    for (const [name, row] of Object.entries(history.files)) {
        assert(Object.isFrozen(row)); assert.equal(sha(Buffer.from(row.source)), row.sha256);
        assert.equal(history.provenance.sources[name].blob, blob(Buffer.from(row.source)));
    }
    for (const name of [workflowPath, ...Object.keys(d.sourceMigrations)]) {
        const before = Buffer.from(readWorkflowHistoricalSource(name)), current = await readFile(path.join(root, name));
        assert.deepEqual(recoverCaptureV34Input(name, current), before);
        assert.deepEqual(recoverCaptureV34Input(name, before), before);
        for (const altered of [Buffer.concat([current, Buffer.from('\n')]), Buffer.concat([before, Buffer.from('\n')]), Buffer.from('unknown')]) {
            assert.throws(() => recoverCaptureV34Input(name, altered));
        }
    }
    const archive = await readFile(new URL('./fixtures/capture-v34-workflow-before.json.gz', import.meta.url));
    assert.equal(sha(archive), d.historySHA256); assert.equal(archive.length, d.historyGzipBytes);
    assert.equal(gunzipSync(archive, {maxOutputLength: 262144}).length, d.historyInflatedBytes);
    const altered = Buffer.from(archive); altered[altered.length - 1] ^= 1;
    for (const input of [altered, Buffer.concat([archive, Buffer.from('\n')]), Buffer.alloc(131073), new Uint8Array(archive)]) {
        assert.throws(() => decodeWorkflowHistory(input));
    }
    assert.throws(() => readWorkflowHistoricalSource('unknown'));
    assert.throws(() => normalizeWorkflowInput(workflowPath, new Uint8Array(0)));
    const untouched = Buffer.from('unowned source');
    assert.equal(normalizeWorkflowInput('unowned', untouched), untouched);
});

test('physical workflow admission refuses old bytes drift missing files symlinks hardlinks and writable aliases', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'workflow-physical-'));
    try {
        const file = path.join(directory, 'input'), alias = path.join(directory, 'alias');
        const current = await readFile(path.join(root, workflowPath)), before = Buffer.from(readWorkflowHistoricalSource(workflowPath));
        await writeFile(file, current, {mode: 0o600});
        assert.deepEqual(readCurrentWorkflowSource(workflowPath, file), current);
        for (const bad of [before, Buffer.concat([current, Buffer.from('\n')]), Buffer.from('unknown')]) {
            await writeFile(file, bad); assert.throws(() => readCurrentWorkflowSource(workflowPath, file));
        }
        await unlink(file); assert.throws(() => readCurrentWorkflowSource(workflowPath, file));
        await writeFile(alias, current, {mode: 0o600}); await symlink(alias, file);
        assert.throws(() => readCurrentWorkflowSource(workflowPath, file)); await unlink(file);
        await link(alias, file); assert.throws(() => readCurrentWorkflowSource(workflowPath, file));
        await unlink(file); await unlink(alias); await writeFile(file, current, {mode: 0o600});
        await chmod(file, 0o622); assert.throws(() => readCurrentWorkflowSource(workflowPath, file));
        assert.throws(() => readCurrentWorkflowSource('unknown', file));
    } finally { await rm(directory, {recursive: true, force: true}); }
});

test('the existing V26 workflow before-image stays with its original CPU owner and cannot satisfy V34 or V35 admission', async () => {
    const retained = d.retainedWorkflowInput;
    assert.equal(retained.archivePath, 'browser-client/tests/fixtures/capture-v26-software-managed-before.json.gz');
    assert.equal(retained.archiveSHA256, '7ba538ec0cc6c4ce352ac670e8b4c926cd9cc0fcc5f49c2aa30f49831e286271');
    const archive = await readFile(path.join(root, retained.archivePath));
    assert.equal(sha(archive), retained.archiveSHA256);
    const previous = JSON.parse(gunzipSync(archive, {maxOutputLength: 524288}));
    const source = Buffer.from(previous.files[workflowPath].source);
    assert.equal(sha(source), 'd608f4173399093959bda9362953a46589d02b08893cc5468c0c09c0de358202');
    assert.equal(sha(source), retained.sha256);
    assert.equal(normalizeRetainedWorkflowInput(workflowPath, source), source);
    assert.throws(() => normalizeWorkflowInput(workflowPath, source));
    assert.throws(() => recoverCaptureV34Input(workflowPath, source));
    for (const bad of [Buffer.concat([source, Buffer.from('\n')]), Buffer.from('unknown')]) {
        assert.throws(() => normalizeRetainedWorkflowInput(workflowPath, bad));
    }
    const directory = await mkdtemp(path.join(tmpdir(), 'workflow-retained-'));
    try {
        const file = path.join(directory, 'input'); await writeFile(file, source, {mode: 0o600});
        assert.throws(() => readCurrentWorkflowSource(workflowPath, file));
    } finally { await rm(directory, {recursive: true, force: true}); }
});

test('V35 shipping gate rejects V34 or invented manifests before reading source', () => fixture(async (source, proposal) => {
    assert.equal((await check(source, proposal)).version, 35);
    for (const wrong of [previousBytes, Buffer.concat([bytes, Buffer.from('\n')]), Buffer.from(JSON.stringify({...manifest, version: 34}))]) {
        await writeFile(proposal, wrong); let reads = 0;
        await assert.rejects(() => gate(assert, async file => { if (file !== proposal) reads++; return readFile(file); },
            realpath, lstat, path, sha, source, proposal));
        assert.equal(reads, 0);
    }
}));

test('V35 shipping gate requires current physical workflow and CPU sources without historical recovery', () => fixture(async (source, proposal, directory) => {
    for (const name of [workflowPath, ...Object.keys(d.sourceMigrations), ...d.addedRows]) {
        const file = path.join(directory, name), current = await readFile(file);
        await writeFile(file, Buffer.concat([current, Buffer.from('\n')])); await assert.rejects(() => check(source, proposal));
        if (name === workflowPath || Object.hasOwn(d.sourceMigrations, name)) {
            await writeFile(file, readWorkflowHistoricalSource(name)); await assert.rejects(() => check(source, proposal));
        }
        await unlink(file); await assert.rejects(() => check(source, proposal));
        const alias = path.join(directory, 'alias'); await writeFile(alias, current); await symlink(alias, file);
        await assert.rejects(() => check(source, proposal));
        await unlink(file); await unlink(alias); await writeFile(file, current);
    }
}));

test('production preparer changes only the admitted manifest digest and imports no history adapter', () => {
    const before = readWorkflowHistoricalSource(preparerPath);
    assert.equal(preparer.split(sha(bytes)).length, 2);
    assert.equal(preparer.replace(sha(bytes), sha(previousBytes)), before);
    for (const forbidden of ['source-fixture', 'recoverCapture', 'normalizeWorkflow', 'readWorkflow', 'normalizeForkRename', 'readForkRename']) {
        assert(!preparer.includes(forbidden));
    }
});
