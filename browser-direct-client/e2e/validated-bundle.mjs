// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// An explicitly reviewed complete artifact digest; this helper does not run
// tests or turn an arbitrary current build into a validated checkpoint.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

export function requireValidatedBundleManifest(bytes, expectedSHA256) {
    assert.ok(typeof expectedSHA256 === 'string' && /^[a-f0-9]{64}$/.test(expectedSHA256),
        'Supply the reviewed complete production bundle-manifest SHA-256.');
    const manifestSHA256 = createHash('sha256').update(bytes).digest('hex');
    assert.equal(manifestSHA256, expectedSHA256, 'The current frozen bundle must match the reviewed artifact.');
    const entries = JSON.parse(Buffer.from(bytes).toString('utf8'));
    assert.ok(Array.isArray(entries));
    for (const entry of entries) {
        assert.ok(typeof entry.path === 'string' && Number.isSafeInteger(entry.bytes) && entry.bytes >= 0
            && typeof entry.sha256 === 'string' && /^[a-f0-9]{64}$/.test(entry.sha256), 'Invalid complete artifact manifest.');
    }
    const productionFiles = {};
    for (const pattern of [/^assets\/index-[^.]+\.js$/, /^assets\/session-worker-[^.]+\.js$/,
        /^assets\/audio-worklet-[^.]+\.js$/, /^asset-worker\.js$/]) {
        const matching = entries.filter(entry => pattern.test(entry.path));
        assert.equal(matching.length, 1, 'Bind exactly one current main, session worker, audio worklet and asset worker.');
        productionFiles[matching[0].path] = matching[0].sha256;
    }
    const sourceMaps = Object.fromEntries(entries.filter(entry => entry.path.endsWith('.js.map'))
        .map(entry => [entry.path, entry.sha256]));
    assert.ok(Object.keys(sourceMaps).length > 0, 'Record the current bundle source-map provenance.');
    return { manifestSHA256, productionFiles, sourceMaps };
}
