// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

function gitBlob(content) {
    return createHash('sha1').update(`blob ${content.length}\0`).update(content).digest('hex');
}

function safeRelative(value) {
    assert.ok(typeof value === 'string' && value.length > 0 && !path.isAbsolute(value)
        && !value.includes('\\') && !value.split('/').includes('..'), 'Renderer paths must stay inside their source roots.');
}

// Default verification uses the committed manifest, without a local topic checkout.
// An explicitly supplied read-only source checkout additionally audits original Git objects.
export async function verifyRendererReuse(root, manifest, { source } = {}) {
    assert.equal(manifest.sourceRepository, 'noah-be/overte');
    assert.match(manifest.sourceRevision, /^[a-f0-9]{40}$/);
    assert.ok(Array.isArray(manifest.files) && manifest.files.length > 0);
    const seen = new Set();
    let unchanged = 0, adapted = 0;
    for (const entry of manifest.files) {
        safeRelative(entry.source); safeRelative(entry.destination);
        assert.ok(!seen.has(entry.destination), `Duplicate renderer destination: ${entry.destination}`);
        seen.add(entry.destination);
        assert.match(entry.gitBlob, /^[a-f0-9]{40}$/);
        assert.ok(Number.isSafeInteger(entry.bytes) && entry.bytes >= 0);
        if (source) {
            const original = execFileSync('git', ['-C', source, 'show', `${manifest.sourceRevision}:${entry.source}`]);
            assert.equal(gitBlob(original), entry.gitBlob, `Original renderer Git object differs: ${entry.source}`);
            assert.equal(original.length, entry.bytes, `Original renderer byte count differs: ${entry.source}`);
        }
        const content = await readFile(path.join(root, entry.destination));
        if (entry.modified) {
            assert.ok(typeof entry.modifications === 'string' && entry.modifications.trim().length > 0,
                `Explain adapted renderer source: ${entry.destination}`);
            assert.match(entry.currentSha256 ?? '', /^[a-f0-9]{64}$/,
                `Adapted renderer source needs a reviewed currentSha256: ${entry.destination}`);
            assert.equal(createHash('sha256').update(content).digest('hex'), entry.currentSha256,
                `Adapted renderer source changed without a reviewed provenance update: ${entry.destination}`);
            assert.ok(content.includes(Buffer.from('Modified for Overte direct browser compatibility'))
                || content.includes(Buffer.from('Browser permission/device lifecycle adapted from the immutable renderer source')),
                `Adapted renderer source needs its modification notice: ${entry.destination}`);
            adapted++;
        } else {
            assert.equal(gitBlob(content), entry.gitBlob, `Immutable renderer source changed: ${entry.destination}`);
            assert.equal(content.length, entry.bytes); unchanged++;
        }
    }
    return { unchanged, adapted };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
    const args = process.argv.slice(2);
    assert.ok(args.length === 0 || (args.length === 2 && args[0] === '--source'),
        'Use --source /path/to/immutable/renderer to audit original Git objects.');
    const source = args.length ? path.resolve(args[1]) : undefined;
    const manifest = JSON.parse(await readFile(path.join(root, 'reuse-manifest.json'), 'utf8'));
    assert.equal(manifest.sourceRevision, '261fc77c1c322410f6096e65dcff0388c372286d');
    assert.ok(manifest.files.length > 60, 'The complete reusable rendering closure must be present');
    const { unchanged, adapted } = await verifyRendererReuse(root, manifest, { source });
    console.log(`Verified ${unchanged} exact source blobs; ${adapted} hash-bound direct-client adaptations${source ? '; original Git objects audited' : ''}.`);
}
