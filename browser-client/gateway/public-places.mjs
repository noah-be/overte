// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { isIP } from 'node:net';
import { viewpointPath } from '../shared/visitor-preferences.mjs';
export { viewpointPath } from '../shared/visitor-preferences.mjs';
import { domainAddress, EXPOSED_PERMISSION_KEYS } from './validation.mjs';

// This is the anonymous Directory Services endpoint used by native AddressManager.
export const PUBLIC_PLACE_ENDPOINT = 'https://mv.overte.org/server/api/v1/places/';
const uuid = value => typeof value === 'string' && (value.length === 36 || (value.length === 38 && value.startsWith('{') && value.endsWith('}'))) && /^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value)
    ? value.replace(/[{}]/g, '').toLowerCase() : null;
const administrative = ['id_can_adjust_locks', 'id_can_replace_content',
    'id_can_get_and_set_private_user_data', 'id_can_kick'];

export function publicPlaceNames(value = '') {
    const names = value.split(',').filter(Boolean);
    if (names.some(name => !/^[a-z0-9_-]{1,64}$/.test(name)) || new Set(names).size !== names.length) {
        throw Error('Public places must be distinct lowercase Directory Services names.');
    }
    return names;
}

export function isPublicIPv4(address) {
    if (typeof address !== 'string' || isIP(address) !== 4) return false;
    const [a, b, c] = address.split('.').map(Number);
    return !(a === 0 || a === 10 || a === 127 || a >= 224 ||
        (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) ||
        (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) ||
        (a === 192 && b === 0 && (c === 0 || c === 2)) || (a === 192 && b === 88 && c === 99) ||
        (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) ||
        (a === 203 && b === 0 && c === 113));
}

export function publicPlaceSelection(domain, configuredNames) {
    const selected = new URL(domainAddress(domain));
    // Select a name from actual operator configuration, never construct a directory
    // request authority from browser input or a directory response.
    const name = configuredNames.find(candidate => candidate === selected.hostname);
    if (!name || selected.port || selected.search) {
        throw Error('This public place is not enabled by the gateway administrator.');
    }
    viewpointPath(selected.pathname);
    return name;
}

export function validatePublicPlace(document, name) {
    const place = document?.data?.place, domain = place?.domain;
    if (document?.status !== 'success' || place?.name !== name || place.visibility !== 'open' ||
        domain?.active !== true || domain.capacity !== 0) {
        throw Error('The public place must be open, active and have unlimited visitor capacity.');
    }
    if (!isPublicIPv4(domain.network_address) || !Number.isSafeInteger(domain.network_port) ||
        domain.network_port < 1 || domain.network_port > 65535) {
        throw Error('The public place must advertise a public IPv4 domain address and valid port.');
    }
    if (typeof domain.protocol_version !== 'string' || !/^[A-Za-z0-9+/]{22}==$/.test(domain.protocol_version)) {
        throw Error('The public place did not advertise a valid native protocol signature.');
    }
    const domainId = uuid(domain.id);
    if (!domainId || domainId === '00000000-0000-0000-0000-000000000000') throw Error('The public place did not advertise a valid domain identity.');
    const spawn = place.path || '';
    if (typeof spawn !== 'string' || spawn.length > 512) {
        throw Error('The public place advertised an unsupported spawn path.');
    }
    return { mode: 'public-native-guest', name, domainId,
        nativeDomain: `overte://${domain.network_address}:${domain.network_port}${viewpointPath(spawn)}`,
        protocolVersion: domain.protocol_version, serverVersion: String(domain.version || '').slice(0, 128),
        capacity: 0 };
}

export async function resolvePublicPlace(name, configuredNames, fetcher = fetch) {
    const configured = configuredNames.find(candidate => candidate === name);
    if (!configured) throw Error('This public place is not enabled by the gateway administrator.');
    const target = new URL(encodeURIComponent(configured), PUBLIC_PLACE_ENDPOINT);
    const response = await fetcher(target, { redirect: 'error', signal: AbortSignal.timeout(15000),
        headers: { 'user-agent': 'Mozilla/5.0 (OverteInterface)' } });
    if (!response.ok) throw Error(`Directory Services returned HTTP ${response.status}.`);
    const chunks = []; let size = 0;
    for await (const chunk of response.body) {
        size += chunk.length;
        if (size > 1024 * 1024) throw Error('Directory Services response exceeds the 1 MiB limit.');
        chunks.push(chunk);
    }
    let document;
    try { document = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
    catch { throw Error('Directory Services returned invalid place information.'); }
    return validatePublicPlace(document, configured);
}

export function validatePublicPermissions(actual, connectedDomain, selectedDomain, connectedDomainId, place) {
    const connected = new URL(domainAddress(connectedDomain));
    const pinned = new URL(selectedDomain);
    // Native AddressManager replaces IP-based shareable URLs with a directory
    // place alias. The actual DomainHandler UUID must match the reviewed record
    // both before and after this display-only transition.
    const permittedAuthority = connected.host === pinned.host || (connected.hostname === place?.name && !connected.port);
    if (!permittedAuthority || !place?.domainId || uuid(connectedDomainId) !== place.domainId || !actual ||
        EXPOSED_PERMISSION_KEYS.some(key => typeof actual[key] !== 'boolean') ||
        !actual.id_can_connect || !actual.id_can_view_asset_urls || administrative.some(key => actual[key])) {
        throw Error('This public domain did not grant a supported anonymous guest session. Domain administration and hidden asset URLs are not supported.');
    }
    // The capacity-bypass bit has no native scripting getter. Directory Services
    // capacity=0 is required instead; no unobserved permission value is invented.
    return { ...actual };
}
