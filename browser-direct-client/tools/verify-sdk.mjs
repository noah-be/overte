// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sdkRoot = path.join(root, 'src/protocol/vircadia');
const manifest = JSON.parse(await readFile(path.join(root, 'vendor-sdk.json'), 'utf8'));
assert.equal(manifest.repository, 'https://github.com/vircadia/vircadia-web-sdk');
assert.equal(manifest.commit, '35cb07ba5d4a7e06d078d762fcd4584099a26959');
assert.equal(manifest.license, 'Apache-2.0');
assert.equal(manifest.schemaVersion, 2);

const args = process.argv.slice(2);
assert.ok(args.length === 0 || (args.length === 2 && args[0] === '--source'), 'Use --source /path/to/immutable/sdk to audit original Git objects.');
const source = args.length ? path.resolve(args[1]) : undefined;
function digest(bytes) { return createHash('sha256').update(bytes).digest('hex'); }
function blob(bytes) { return createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex'); }
function safeRelative(value) {
    assert.ok(typeof value === 'string' && value.length > 0 && !path.isAbsolute(value)
        && !value.split(/[\\/]/).includes('..') && !value.includes('\\'), 'Manifest paths must stay inside their source roots.');
}
async function allFiles(directory, prefix = '') {
    const result = [];
    for (const item of await readdir(directory, { withFileTypes: true })) {
        const relative = prefix + item.name;
        assert.ok(!item.isSymbolicLink(), `SDK inputs cannot be symlinks: ${relative}`);
        if (item.isDirectory()) result.push(...await allFiles(path.join(directory, item.name), relative + '/'));
        else if (item.isFile()) result.push(relative);
    }
    return result;
}

const expected = new Set();
const seen = new Set();
const actualFiles = await allFiles(sdkRoot);
const counts = { retained: 0, adapted: 0, omitted: 0 };
for (const entry of manifest.files) {
    safeRelative(entry.path); safeRelative(entry.sourcePath);
    assert.ok(!seen.has(entry.path), `Duplicate SDK destination: ${entry.path}`);
    seen.add(entry.path);
    assert.match(entry.sourceBlob, /^[a-f0-9]{40}$/);
    assert.match(entry.sha256, /^[a-f0-9]{64}$/);
    assert.ok(Object.hasOwn(counts, entry.status), `Missing provenance status: ${entry.path}`);
    counts[entry.status]++;
    if (source) {
        const original = execFileSync('git', ['-C', source, 'show', `${manifest.commit}:${entry.sourcePath}`]);
        assert.equal(blob(original), entry.sourceBlob, `Original SDK Git object differs: ${entry.path}`);
        assert.equal(digest(original), entry.sha256, `Original SDK bytes differ: ${entry.path}`);
    }
    if (entry.status === 'omitted') {
        assert.ok(entry.modifications?.length, `Explain omitted SDK source: ${entry.path}`);
        assert.ok(!actualFiles.includes(entry.path), `Omitted source was accidentally restored: ${entry.path}`);
        continue;
    }
    expected.add(entry.path);
    const bytes = await readFile(path.join(sdkRoot, entry.path));
    assert.equal(digest(bytes), entry.currentSha256, `SDK content changed without a reviewed provenance update: ${entry.path}`);
    if (entry.status === 'retained') {
        assert.equal(entry.currentSha256, entry.sha256, `Retained SDK source must be exact: ${entry.path}`);
        assert.equal(blob(bytes), entry.sourceBlob, `Retained SDK Git blob differs: ${entry.path}`);
    } else {
        assert.ok(entry.modifications?.length, `Explain adapted SDK source: ${entry.path}`);
        assert.ok(bytes.includes(Buffer.from('Modified for Overte direct browser compatibility')), `Adapted source needs its modification notice: ${entry.path}`);
    }
}
assert.deepEqual(actualFiles.sort(), [...expected].sort(), 'Every vendored SDK input must have recorded provenance.');
console.log(`Verified SDK provenance: ${counts.retained} exact inputs, ${counts.adapted} documented adaptations, ${counts.omitted} explicit omissions${source ? '; original Git objects audited' : ''}.`);
