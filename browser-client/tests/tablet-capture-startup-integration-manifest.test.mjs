// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Current physical source admission is independent of both historical CPU cohorts.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdtemp, mkdir, rm, lstat, realpath, unlink, symlink} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {normalizeStartupIntegrationInput, readStartupIntegrationParentSource, decodeStartupIntegrationHistory} from './integration/capture-startup-integration-source-fixture.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const bytes = await readFile(new URL('./fixtures/capture-startup-integration-v33-complete-source-manifest.json', import.meta.url));
const manifest = JSON.parse(bytes), derivation = manifest.startupIntegrationDerivation;
const previousBytes = await readFile(new URL('./fixtures/capture-movement-input-v32-complete-source-manifest.json', import.meta.url));
const previous = JSON.parse(previousBytes);
const startupBytes = await readFile(new URL('./fixtures/capture-startup-runtime-v31-complete-source-manifest.json', import.meta.url));
const startup = JSON.parse(startupBytes);
const preparer = await readFile(new URL('./integration/prepare-tablet-capture-acceptance.mjs', import.meta.url), 'utf8');
const start = preparer.indexOf('const manifestBytes=await readFile(proposal);');
const end = preparer.indexOf('const directory=await mkdtemp(', start);
assert(start >= 0 && end > start);
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const gate = new AsyncFunction('assert', 'readFile', 'realpath', 'lstat', 'path', 'sha', 'source', 'proposal', preparer.slice(start, end) + 'return m;');

async function fixture(fn) {
    const directory = await mkdtemp(path.join(tmpdir(), 'capture-startup-integration-'));
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

test('V33 retains both parent row sets and records every physical source change', async () => {
    assert.equal(manifest.version, 33);
    assert.equal(derivation.previousManifestSHA256, digest(previousBytes));
    assert.equal(derivation.startupManifestSHA256, digest(startupBytes));
    assert.equal(new Set(manifest.files.map(row => row.path)).size, manifest.files.length);
    for (const row of manifest.files) assert.equal(digest(await readFile(path.join(root, row.path))), row.afterSHA256);
    for (const row of [...previous.files, ...startup.files]) assert(manifest.files.some(current => current.path === row.path));
    for (const row of previous.files) {
        const change = derivation.sourceMigrations[row.path];
        assert.deepEqual(manifest.files.find(current => current.path === row.path), change ? {...row, beforeSHA256: row.afterSHA256, afterSHA256: change.afterSHA256, bytes: change.bytes} : row);
    }
    const expected = structuredClone(previous);
    Object.assign(expected, {version: 33, scope: manifest.scope, files: manifest.files, startupIntegrationDerivation: derivation});
    assert.deepEqual(manifest, expected);
    assert.equal(derivation.productionHistoryFallback, false);
    assert.equal(derivation.actualRuntimeAcceptance, false);
    for (const [name, hash] of Object.entries(derivation.unchangedAcceptanceSourcePins)) assert.equal(digest(await readFile(path.join(root, name))), hash);
});

test('shipping gate admits exact V33 and rejects either parent before reading source', () => fixture(async (source, proposal) => {
    assert.equal((await gate(assert, readFile, realpath, lstat, path, digest, source, proposal)).version, 33);
    assert(!preparer.includes('source-fixture')); assert(!preparer.includes('recoverCapture')); assert(!preparer.includes('normalizeStartup'));
    for (const wrong of [previousBytes, startupBytes, Buffer.concat([bytes, Buffer.from('\n')])]) {
        await writeFile(proposal, wrong); let sourceReads = 0;
        await assert.rejects(() => gate(assert, async file => { if (file !== proposal) sourceReads++; return readFile(file); }, realpath, lstat, path, digest, source, proposal));
        assert.equal(sourceReads, 0);
    }
}));

test('every migrated and admitted browser source refuses drift missing files and aliases', () => fixture(async (source, proposal, directory) => {
    for (const name of [...Object.keys(derivation.sourceMigrations), ...derivation.addedRows].filter(name => name.startsWith('browser-client/'))) {
        const file = path.join(directory, name), current = await readFile(file);
        await writeFile(file, Buffer.concat([current, Buffer.from('\n')]));
        await assert.rejects(() => gate(assert, readFile, realpath, lstat, path, digest, source, proposal));
        await unlink(file);
        await assert.rejects(() => gate(assert, readFile, realpath, lstat, path, digest, source, proposal));
        const alias = path.join(directory, 'alias'); await writeFile(alias, current); await symlink(alias, file);
        await assert.rejects(() => gate(assert, readFile, realpath, lstat, path, digest, source, proposal));
        await unlink(file); await unlink(alias); await writeFile(file, current);
    }
}));

test('both CPU parent histories retain exact bytes and refuse unknown inputs', async () => {
    for (const [profile, rows] of Object.entries(derivation.currentNormalizedSourceSHA256)) {
        for (const [name, hash] of Object.entries(rows)) {
            const current = await readFile(path.join(root, name)), parent = Buffer.from(readStartupIntegrationParentSource(profile, name));
            assert.equal(digest(current), hash);
            assert.deepEqual(normalizeStartupIntegrationInput(profile, name, current), parent);
            assert.deepEqual(normalizeStartupIntegrationInput(profile, name, parent), parent);
            assert.throws(() => normalizeStartupIntegrationInput(profile, name, Buffer.concat([current, Buffer.from('\n')])));
        }
    }
    for (const [name, hash] of Object.entries(derivation.originalAssertionBodiesSHA256)) {
        const text = await readFile(path.join(root, name), 'utf8');
        assert.equal(digest(Buffer.from(text.slice(text.indexOf("test('")))), hash);
    }
    const archive = await readFile(new URL('./fixtures/capture-startup-integration-parents.json.gz', import.meta.url));
    assert(Object.isFrozen(decodeStartupIntegrationHistory(archive)));
    const altered = Buffer.from(archive); altered[altered.length - 1] ^= 1;
    assert.throws(() => decodeStartupIntegrationHistory(altered));
    assert.throws(() => decodeStartupIntegrationHistory(Buffer.alloc(262145)));
    assert.throws(() => normalizeStartupIntegrationInput('unknown', 'unknown', Buffer.alloc(0)));
    assert.throws(() => readStartupIntegrationParentSource('startup', 'unknown'));
});
