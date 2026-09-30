// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { lookup } from 'node:dns/promises';

// Asset bodies can be HTML/SVG; a direct navigation must never inherit the gateway origin.
export const ASSET_SANDBOX_POLICY = "sandbox; script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

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
