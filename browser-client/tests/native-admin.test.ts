// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { nativeAdminCredential } from '../lab/native-admin.mjs';

test('native administrator credentials are fresh 256-bit machine tokens with compatible verifiers', () => {
    const generated = Array.from({ length: 16 }, () => nativeAdminCredential());
    assert.equal(new Set(generated.map(value => value.token)).size, generated.length);
    for (const value of generated) {
        assert.match(value.token, /^[0-9a-f]{64}$/);
        assert.equal(value.nativeVerifier, createHash('sha256').update(value.token).digest('hex'));
        assert.notEqual(value.nativeVerifier, value.token);
    }
    assert.throws(() => Reflect.apply(nativeAdminCredential, undefined, ['human-password']), TypeError);
});

test('Python laboratory provisioning uses the same no-input random credential boundary', () => {
    const directory = fileURLToPath(new URL('../lab/', import.meta.url));
    execFileSync('python3', ['-c', `
import hashlib, re, sys
sys.path.insert(0, sys.argv[1])
from native_admin import native_admin_credential
values = [native_admin_credential() for _ in range(16)]
assert len({value['token'] for value in values}) == 16
for value in values:
    assert re.fullmatch('[0-9a-f]{64}', value['token'])
    assert value['nativeVerifier'] == hashlib.sha256(value['token'].encode('ascii')).hexdigest()
    assert value['nativeVerifier'] != value['token']
try:
    native_admin_credential('human-password')
except TypeError:
    pass
else:
    raise AssertionError('The credential generator must not accept a supplied secret')
`, directory], { stdio: ['ignore', 'pipe', 'pipe'] });
});
