// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
// JavaScript helper is the same implementation used by the production gateway.
// @ts-expect-error JavaScript module intentionally has no generated declaration file.
import { PERMISSION_KEYS, readPolicyFile, validatePermissionPolicy } from '../gateway/permission-policy.mjs';

const domain = 'overte://127.0.0.1:45102';
const row = (name: string) => ({ permissions_id: name, ...Object.fromEntries(PERMISSION_KEYS.map((key: string) => [key, ['id_can_connect', 'id_can_view_asset_urls'].includes(key)])) });
function settings(): any { return { version: 2.7, security: { standard_permissions: [row('anonymous'), row('localhost')], ip_permissions: [], machine_fingerprint_permissions: [] }, authentication: { enable_oauth2: false } }; }

test('anonymous-baseline policy accepts equal guest permissions and emits runtime API expectations', () => {
    const policy = validatePermissionPolicy({ domain, settings: settings() });
    assert.equal(policy.mode, 'anonymous-baseline');
    assert.equal(policy.nativePermissions.canViewAssetURLs, true);
    assert.equal(policy.nativePermissions.canWriteAssets, false);
    assert.equal(policy.nativePermissions.canGetAndSetPrivateUserData, false);
});
test('localhost elevated rights are rejected even when guest can connect', () => {
    const value = settings(); value.security.standard_permissions[1].id_can_rez = true;
    assert.throws(() => validatePermissionPolicy({ domain, settings: value }), /beyond the anonymous guest baseline/);
});
test('IP denial and fingerprint overrides cannot be represented by the proxy and fail closed', () => {
    for (const key of ['ip_permissions', 'machine_fingerprint_permissions']) {
        const value = settings(); value.security[key] = [{ permissions_id: '192.0.2.1', id_can_connect: false }];
        assert.throws(() => validatePermissionPolicy({ domain, settings: value }), /identity-preserving server transport/);
    }
});
test('all dangerous permissions are rejected even if localhost and anonymous agree', () => {
    for (const key of ['id_can_adjust_locks', 'id_can_write_to_asset_server', 'id_can_connect_past_max_capacity', 'id_can_kick', 'id_can_replace_content', 'id_can_get_and_set_private_user_data']) {
        const value = settings(); value.security.standard_permissions.forEach((item: any) => { item[key] = true; });
        assert.throws(() => validatePermissionPolicy({ domain, settings: value }), /administrative guest permission/);
    }
});
test('missing, loosely typed, unknown or duplicate permission fields are rejected', () => {
    const missing = settings(); delete missing.security.standard_permissions[0].id_can_kick;
    assert.throws(() => validatePermissionPolicy({ domain, settings: missing }), /explicit boolean/);
    const loose = settings(); loose.security.standard_permissions[0].id_can_connect = 'false';
    assert.throws(() => validatePermissionPolicy({ domain, settings: loose }), /explicit boolean/);
    const unknown = settings(); unknown.security.standard_permissions[0].id_can_new_permission = true;
    assert.throws(() => validatePermissionPolicy({ domain, settings: unknown }), /unknown permission/);
    const duplicate = settings(); duplicate.security.standard_permissions.push(row('anonymous'));
    assert.throws(() => validatePermissionPolicy({ domain, settings: duplicate }), /exactly one anonymous/);
});
test('authenticated and restricted-access domains are not silently downgraded to anonymous', () => {
    const oauth = settings(); oauth.authentication.enable_oauth2 = true;
    assert.throws(() => validatePermissionPolicy({ domain, settings: oauth }), /authenticated domains/);
    const restricted = settings(); restricted.security.restricted_access = true;
    assert.throws(() => validatePermissionPolicy({ domain, settings: restricted }), /restricted-access/);
});
test('unreviewed or missing settings versions cannot trigger silent permission migration', () => {
    for (const version of [undefined, 2.6, 2.8]) {
        const value = settings(); value.version = version;
        assert.throws(() => validatePermissionPolicy({ domain, settings: value }), /schema version 2.7/);
    }
});
test('policy maps exact configured domains to re-read actual files and rejects changes and unmatched domains', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-permission-test-'));
    const actual = path.join(directory, 'domain.json'), file = path.join(directory, 'policy.json');
    try {
        await writeFile(actual, JSON.stringify(settings()));
        await writeFile(file, JSON.stringify({ version: 1, mode: 'anonymous-baseline', domains: [{ domain, settingsFile: actual }] }));
        const policies = await readPolicyFile(file, [domain]);
        assert.equal(policies.get(domain).settingsFile, actual);
        await assert.rejects(() => readPolicyFile(file, ['overte://127.0.0.1:45103']), /outside the configured allowlist/);
        await assert.rejects(() => readPolicyFile(file, [domain, 'overte://127.0.0.1:45103']), /every configured domain/);
        const changed = settings(); changed.security.standard_permissions[1].id_can_write_to_asset_server = true;
        await writeFile(actual, JSON.stringify(changed));
        await assert.rejects(() => readPolicyFile(file, [domain]), /beyond the anonymous guest baseline/);
        await writeFile(actual, '{private data must not appear in the error');
        await assert.rejects(() => readPolicyFile(file, [domain]), error => error instanceof Error && error.message.endsWith('actual domain settings file is not valid JSON.'));
        await rm(actual);
        await assert.rejects(() => readPolicyFile(file, [domain]), /actual domain settings file is unavailable/);
    } finally { await rm(directory, { recursive: true, force: true }); }
});
