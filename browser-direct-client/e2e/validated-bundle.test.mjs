// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { requireValidatedBundleManifest } from './validated-bundle.mjs';
const manifest = Buffer.from(JSON.stringify(['assets/index-current.js', 'assets/session-worker-current.js',
    'assets/audio-worklet-current.js', 'asset-worker.js', 'assets/index-current.js.map']
    .map(path => ({ path, bytes: 123, sha256: 'b'.repeat(64) }))));
const digest = value => createHash('sha256').update(value).digest('hex');
test('the explicitly qualified complete current artifact binds production and source-map files', () => {
    const proof = requireValidatedBundleManifest(manifest, digest(manifest));
    assert.equal(proof.manifestSHA256, digest(manifest));
    assert.deepEqual(Object.keys(proof.productionFiles), ['assets/index-current.js', 'assets/session-worker-current.js',
        'assets/audio-worklet-current.js', 'asset-worker.js']);
    assert.deepEqual(proof.sourceMaps, { 'assets/index-current.js.map': 'b'.repeat(64) });
});
test('absent/malformed qualification or a changed artifact cannot silently use a new build', () => {
    for (const value of [undefined, null, '', 'a'.repeat(63), 'A'.repeat(64), 'z'.repeat(64)]) {
        assert.throws(() => requireValidatedBundleManifest(manifest, value), /reviewed complete/);
    }
    const changed = Buffer.from(manifest); changed[changed.indexOf('current')] = 'C'.charCodeAt(0);
    assert.throws(() => requireValidatedBundleManifest(changed, digest(manifest)), /reviewed artifact/);
});
test('an explicitly supplied digest still cannot hide missing workers or ambiguous production entries', () => {
    const entries = JSON.parse(manifest);
    for (const modified of [entries.filter(row => row.path !== 'asset-worker.js'), [...entries, entries[0]],
        entries.filter(row => !row.path.endsWith('.map'))]) {
        const bytes = Buffer.from(JSON.stringify(modified));
        assert.throws(() => requireValidatedBundleManifest(bytes, digest(bytes)));
    }
});
