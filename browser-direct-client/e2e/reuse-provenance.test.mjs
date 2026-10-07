// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { verifyRendererReuse } from '../tools/verify-reuse.mjs';

const original = Buffer.from('// SPDX-License-Identifier: Apache-2.0\nexport const sampleRate = 48000;\n');
const adapted = Buffer.from('// SPDX-License-Identifier: Apache-2.0\n// Modified for Overte direct browser compatibility.\nexport const sampleRate = 24000;\n');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
// Git itself provides the original object identity independently of the checker.
const originalBlob = execFileSync('git', ['hash-object', '--stdin'], { input: original, encoding: 'utf8' }).trim();

async function fixture(t) {
    const root = await mkdtemp(path.join(tmpdir(), 'overte-renderer-provenance-'));
    t.after(() => rm(root, { recursive: true, force: true }));
    await mkdir(path.join(root, 'src'));
    await writeFile(path.join(root, 'src/exact.js'), original);
    await writeFile(path.join(root, 'src/adapted.js'), adapted);
    const manifest = { sourceRepository: 'noah-be/overte', sourceRevision: '1'.repeat(40), files: [
        { source: 'browser-client/src/exact.js', destination: 'src/exact.js', gitBlob: originalBlob, bytes: original.length },
        { source: 'browser-client/src/adapted.js', destination: 'src/adapted.js', gitBlob: originalBlob, bytes: original.length,
            modified: true, modifications: 'Use native 24 kHz framing.', currentSha256: digest(adapted) },
    ] };
    return { root, manifest };
}

test('portable renderer provenance audits exact and adapted bytes without an original checkout', async t => {
    const { root, manifest } = await fixture(t);
    assert.deepEqual(await verifyRendererReuse(root, manifest), { unchanged: 1, adapted: 1 });
});

test('same-length adapted-file tampering fails despite retained modification text and original metadata', async t => {
    const { root, manifest } = await fixture(t);
    const output = path.join(root, 'src/adapted.js');
    const changed = (await readFile(output, 'utf8')).replace('24000', '12000');
    assert.equal(Buffer.byteLength(changed), adapted.length);
    await writeFile(output, changed);
    await assert.rejects(verifyRendererReuse(root, manifest), /changed without a reviewed provenance update/);
});

test('adapted renderer entries fail closed when the reviewed current hash is missing or malformed', async t => {
    const { root, manifest } = await fixture(t);
    delete manifest.files[1].currentSha256;
    await assert.rejects(verifyRendererReuse(root, manifest), /needs a reviewed currentSha256/);
    manifest.files[1].currentSha256 = 'not-a-sha256';
    await assert.rejects(verifyRendererReuse(root, manifest), /needs a reviewed currentSha256/);
});

test('recorded adapted bytes still require a prominent modification notice', async t => {
    const { root, manifest } = await fixture(t);
    await writeFile(path.join(root, 'src/adapted.js'), original);
    manifest.files[1].currentSha256 = digest(original);
    await assert.rejects(verifyRendererReuse(root, manifest), /needs its modification notice/);
});

test('exact renderer sources retain their original Git-object check', async t => {
    const { root, manifest } = await fixture(t);
    await writeFile(path.join(root, 'src/exact.js'), original.toString().replace('48000', '24000'));
    await assert.rejects(verifyRendererReuse(root, manifest), /Immutable renderer source changed/);
});

test('explicit original-checkout audit checks adapted originals rather than their current hashes', async t => {
    const { root, manifest } = await fixture(t);
    const source = path.join(root, 'original-checkout');
    await mkdir(path.join(source, 'browser-client/src'), { recursive: true });
    await writeFile(path.join(source, 'browser-client/src/exact.js'), original);
    await writeFile(path.join(source, 'browser-client/src/adapted.js'), original);
    const git = arguments_ => execFileSync('git', ['-C', source, '-c', `core.hooksPath=${path.join(root, 'empty-hooks')}`,
        '-c', 'commit.gpgsign=false', '-c', 'user.name=Renderer provenance fixture',
        '-c', 'user.email=provenance-fixture@example.invalid', ...arguments_], { encoding: 'utf8' }).trim();
    git(['init', '--quiet']); git(['add', '.']); git(['commit', '--quiet', '-m', 'Immutable renderer fixture']);
    manifest.sourceRevision = git(['rev-parse', 'HEAD']);
    assert.deepEqual(await verifyRendererReuse(root, manifest, { source }), { unchanged: 1, adapted: 1 });
    manifest.files[1].gitBlob = '0'.repeat(40);
    await assert.rejects(verifyRendererReuse(root, manifest, { source }), /Original renderer Git object differs/);
});
