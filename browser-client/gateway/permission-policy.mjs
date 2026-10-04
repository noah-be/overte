// SPDX-License-Identifier: Apache-2.0
// This validates operator-managed anonymous domain configuration. It cannot attest remote server settings
// or recover the original browser IP, hardware fingerprint, or authenticated identity through a native proxy.
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { domainAddress } from './validation.mjs';

export const PERMISSION_KEYS = Object.freeze([
    'id_can_connect', 'id_can_rez_avatar_entities', 'id_can_adjust_locks', 'id_can_rez', 'id_can_rez_tmp',
    'id_can_write_to_asset_server', 'id_can_connect_past_max_capacity', 'id_can_kick', 'id_can_replace_content',
    'id_can_get_and_set_private_user_data', 'id_can_view_asset_urls',
]);
export const NATIVE_PERMISSION_KEYS = Object.freeze({
    id_can_rez_avatar_entities: 'canRezAvatarEntities', id_can_adjust_locks: 'canAdjustLocks',
    id_can_rez: 'canRez', id_can_rez_tmp: 'canRezTmp', id_can_write_to_asset_server: 'canWriteAssets',
    id_can_kick: 'canKick', id_can_get_and_set_private_user_data: 'canGetAndSetPrivateUserData',
    id_can_view_asset_urls: 'canViewAssetURLs', id_can_replace_content: 'canReplaceContent',
});
const ADMIN_PERMISSIONS = Object.freeze([
    'id_can_adjust_locks', 'id_can_write_to_asset_server', 'id_can_connect_past_max_capacity',
    'id_can_kick', 'id_can_replace_content', 'id_can_get_and_set_private_user_data',
]);
const record = value => !!value && typeof value === 'object' && !Array.isArray(value);
const failure = detail => { throw new Error(`Anonymous gateway policy rejected: ${detail}`); };

function permissionRow(rows, name) {
    const matches = rows.filter(row => record(row) && typeof row.permissions_id === 'string' && row.permissions_id.toLowerCase() === name);
    if (matches.length !== 1) failure(`exactly one ${name} permission row is required.`);
    const row = matches[0];
    for (const key of Object.keys(row)) if (key.startsWith('id_can_') && !PERMISSION_KEYS.includes(key)) failure('an unknown permission requires policy review.');
    for (const key of PERMISSION_KEYS) if (typeof row[key] !== 'boolean') failure(`explicit boolean ${key} is required in the ${name} row.`);
    return Object.fromEntries(PERMISSION_KEYS.map(key => [key, row[key]]));
}

export function validatePermissionPolicy({ domain, settings }) {
    const canonical = domainAddress(domain);
    if (!record(settings) || !record(settings.security)) failure('actual domain security settings are required.');
    if (settings.version !== 2.7) failure('the reviewed domain settings schema version 2.7 is required; migrate and review server settings before using the gateway.');
    const security = settings.security;
    if (!Array.isArray(security.standard_permissions)) failure('explicit standard permissions are required.');
    for (const key of ['ip_permissions', 'machine_fingerprint_permissions']) {
        if (security[key] !== undefined && (!Array.isArray(security[key]) || security[key].length !== 0)) {
            failure('source IP or machine fingerprint rules require an updated identity-preserving server transport.');
        }
    }
    if (settings.authentication !== undefined && !record(settings.authentication)) failure('invalid domain authentication settings.');
    if (settings.authentication?.enable_oauth2 !== undefined && settings.authentication.enable_oauth2 !== false) {
        failure('authenticated domains require an updated identity-preserving server transport.');
    }
    // Legacy restricted-access configurations may be migrated into permission rows at startup.
    if ((security.restricted_access !== undefined && security.restricted_access !== false) || (security.allowed_users !== undefined && (!Array.isArray(security.allowed_users) || security.allowed_users.length))) {
        failure('legacy restricted-access settings are not supported by this anonymous gateway.');
    }
    const anonymous = permissionRow(security.standard_permissions, 'anonymous');
    const localhost = permissionRow(security.standard_permissions, 'localhost');
    for (const key of PERMISSION_KEYS) if (localhost[key] && !anonymous[key]) failure(`localhost grants ${key} beyond the anonymous guest baseline.`);
    if (!anonymous.id_can_connect || !anonymous.id_can_view_asset_urls) failure('anonymous connect and asset URL viewing must be enabled.');
    for (const key of ADMIN_PERMISSIONS) if (anonymous[key]) failure(`administrative guest permission ${key} is not supported.`);
    const nativePermissions = Object.fromEntries(Object.entries(NATIVE_PERMISSION_KEYS).map(([key, nativeKey]) => [nativeKey, anonymous[key]]));
    return Object.freeze({ domain: canonical, permissions: Object.freeze(anonymous), nativePermissions: Object.freeze(nativePermissions), mode: 'anonymous-baseline' });
}

async function jsonFile(filename, description) {
    let data;
    try { data = await readFile(filename, 'utf8'); } catch { failure(`${description} is unavailable.`); }
    if (data.length > 4 * 1024 * 1024) failure(`${description} exceeds its size limit.`);
    try { return JSON.parse(data); } catch { failure(`${description} is not valid JSON.`); }
}

/** Re-read both mapping and actual domain files; callers must invalidate active sessions when validation fails. */
export async function readPolicyFile(filename, configuredDomains) {
    if (typeof filename !== 'string' || !path.isAbsolute(filename)) failure('an absolute operator-managed policy file is required.');
    if (!Array.isArray(configuredDomains) || !configuredDomains.length) failure('an explicit domain allowlist is required.');
    const allowlist = new Set(configuredDomains.map(domainAddress));
    const config = await jsonFile(filename, 'gateway policy file');
    if (!record(config) || config.version !== 1 || config.mode !== 'anonymous-baseline' || !Array.isArray(config.domains) || config.domains.length === 0) {
        failure('policy version 1 and anonymous-baseline mode with domain mappings are required.');
    }
    const result = new Map();
    for (const entry of config.domains) {
        if (!record(entry) || typeof entry.domain !== 'string' || typeof entry.settingsFile !== 'string' || !path.isAbsolute(entry.settingsFile)) {
            failure('each exact domain must map to an absolute actual domain settings file.');
        }
        const domain = domainAddress(entry.domain);
        if (!allowlist.has(domain)) failure('the policy contains a domain outside the configured allowlist.');
        if (result.has(domain)) failure('duplicate domain policy mappings are not allowed.');
        const settings = await jsonFile(entry.settingsFile, 'actual domain settings file');
        const policy = validatePermissionPolicy({ domain, settings });
        result.set(domain, Object.freeze({ ...policy, settingsFile: entry.settingsFile }));
    }
    if ([...allowlist].some(domain => !result.has(domain))) failure('every configured domain needs its own validated settings mapping.');
    return result;
}
