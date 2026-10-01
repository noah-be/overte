// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';

export function managedUDPDomain(domain, configuredPorts) {
    const url = new URL(domain);
    const address = url.hostname;
    if (isIP(address) !== 4 || !address.startsWith('127.') || address === '127.0.0.1') {
        throw Error('Managed isolated domains require a dedicated loopback IPv4 address.');
    }
    const parts = typeof configuredPorts === 'string' ? configuredPorts.split(',') : [];
    if (!parts.length || parts.length > 32 || parts.some(value => !/^\d{1,5}$/.test(value))) {
        throw Error('Configure OVERTE_GATEWAY_MANAGED_UDP_PORTS with the exact domain and assignment UDP ports.');
    }
    const ports = parts.map(Number);
    if (ports.some(value => value < 1 || value > 65535) || new Set(ports).size !== ports.length || !ports.includes(Number(url.port || 40102))) {
        throw Error('Managed UDP ports must be distinct valid ports including this domain server port.');
    }
    return { address, ports };
}

// Asset bodies can be HTML/SVG; a direct navigation must never inherit the gateway origin.
export const ASSET_SANDBOX_POLICY = "sandbox; script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

export function approvedAssetAddress(input, configuredOrigins) {
    const requested = new URL(input);
    if (!['https:', 'http:'].includes(requested.protocol) || requested.username || requested.password) {
        throw Error('The asset origin is not enabled by the gateway administrator.');
    }
    // Select the authority from actual administrator configuration. Only the resource
    // path and query may come from world data; never fetch its original URL object.
    const approvedOrigin = [...configuredOrigins].find(origin => origin === requested.origin);
    if (!approvedOrigin) throw Error('The asset origin is not enabled by the gateway administrator.');
    const destination = new URL(approvedOrigin);
    if (!['https:', 'http:'].includes(destination.protocol) || destination.username || destination.password || destination.href !== `${destination.origin}/`) {
        throw Error('Asset origins must be plain HTTP(S) origins without credentials, paths or fragments.');
    }
    destination.pathname = requested.pathname;
    destination.search = requested.search;
    return destination;
}

export async function nativeDomainAddress(domain, resolver = lookup) {
    const url = new URL(domain);
    const hostname = url.hostname.replace(/^\[|\]$/g, '');
    const addresses = await resolver(hostname, { all: true });
    const selected = addresses.find(({ family }) => family === 4) || addresses[0];
    if (!selected || selected.address === '127.0.0.1' || /^::ffff:(?:127\.0\.0\.1|7f00:1)$/i.test(selected.address)) {
        throw Error('Native Interface overrides 127.0.0.1 domain ports through shared memory. Use a dedicated loopback address such as 127.0.0.2 for this domain.');
    }
    // Pin the native destination: a second DNS lookup must not change the vetted address.
    url.hostname = selected.address.includes(':') ? `[${selected.address}]` : selected.address;
    return domainAddress(url.href);
}

export function domainAddress(value) {
    if (typeof value !== 'string' || value.length > 1024) throw Error('Enter a valid domain address.');
    const url = new URL(value.includes('://') ? value : `overte://${value}`);
    if (!['overte:', 'hifi:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.hash) {
        throw Error('Only Overte domain addresses are supported.');
    }
    url.protocol = 'overte:';
    return url.href;
}
export function pose(value) {
    const finite = (v, names, limit) => v && names.every(n => typeof v[n] === 'number' && Number.isFinite(v[n]) && Math.abs(v[n]) < limit);
    if (!finite(value.position, ['x', 'y', 'z'], 32768) || !finite(value.orientation, ['x', 'y', 'z', 'w'], 1.01)) throw Error('Invalid avatar pose.');
    const q = value.orientation;
    if (Math.abs(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w - 1) > 0.02) throw Error('Invalid avatar orientation.');
    if (value.velocity && !finite(value.velocity, ['x', 'y', 'z'], 100)) throw Error('Invalid avatar velocity.');
    return { type: 'pose', position: value.position, orientation: value.orientation, velocity: value.velocity };
}
export function nativePoseRequest(value, revision) {
    if (value.permissionRevision !== revision || !Number.isSafeInteger(revision) || revision < 1 ||
        typeof value.nonce !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value.nonce)) {
        throw Error('Invalid native navigation request.');
    }
    const validated = pose(value);
    return { type: 'poseRequest', nonce: value.nonce, permissionRevision: revision,
        position: validated.position, orientation: validated.orientation };
}
export const EXPOSED_PERMISSION_KEYS = ['id_can_connect', 'id_can_rez', 'id_can_rez_tmp', 'id_can_rez_avatar_entities',
    'id_can_view_asset_urls', 'id_can_adjust_locks', 'id_can_write_to_asset_server', 'id_can_replace_content',
    'id_can_get_and_set_private_user_data', 'id_can_kick'];
export function validateNativePermissions(actual, expected, connectedDomain, selectedDomain) {
    const domain = domainAddress(connectedDomain);
    if (new URL(domain).host !== new URL(selectedDomain).host || !actual ||
        EXPOSED_PERMISSION_KEYS.some(key => typeof actual[key] !== 'boolean' || actual[key] !== expected[key])) {
        throw Error('The native domain permissions do not match the verified anonymous visitor policy. Connection denied.');
    }
}
