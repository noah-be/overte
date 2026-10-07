// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { domainAddress } from './validation.mjs';
import { publicPlaceSelection, resolvePublicPlace, viewpointPath } from './public-places.mjs';

const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function validateNativeNavigation(message, revision) {
    if (!message || !UUID.test(message.nonce) || !Number.isSafeInteger(message.permissionRevision)
        || message.permissionRevision < 1 || message.permissionRevision !== revision) throw Error('Invalid native navigation authority.');
    if (message.type === 'navigationHistoryRequest') {
        if (!['back', 'forward'].includes(message.direction)) throw Error('Invalid native navigation history direction.');
        return { type: 'navigationHistory', nonce: message.nonce, permissionRevision: revision, direction: message.direction };
    }
    if (message.type !== 'navigationRequest' || typeof message.address !== 'string' || message.address.length > 1024) throw Error('Invalid native navigation target.');
    // Validate transport authority and bounds here. An ordinary address typed
    // in the real Places GUI may be unsupported (including a blank address).
    // Destination parsing belongs to admission, whose refusal preserves the
    // authorized current world instead of treating user input as forged data.
    return { nonce: message.nonce, permissionRevision: revision, address: message.address };
}

export function managedNavigationSelection(address, domains) {
    const selected = domainAddress(address), url = new URL(selected);
    if (url.search) throw Error('Managed navigation does not support query parameters.');
    const configuredDomain = domains.find(domain => new URL(domain).host === url.host);
    if (!configuredDomain) return null;
    if (selected === configuredDomain) return { configuredDomain, domain: selected };
    const path = viewpointPath(url.pathname);
    const target = new URL(configuredDomain); target.pathname = path; target.search = '';
    return { configuredDomain, domain: target.href };
}

export async function admittedNavigationTarget(address, { domains, publicPlaces, resolve = resolvePublicPlace }) {
    const selected = domainAddress(address);
    const managed = managedNavigationSelection(selected, domains);
    if (managed) return managed.domain;
    const url = new URL(selected);
    const path = viewpointPath(url.pathname);
    if (url.search) throw Error('Place navigation does not support query parameters.');
    if (publicPlaces.includes(url.hostname)) {
        publicPlaceSelection(selected, publicPlaces);
        await resolve(url.hostname, publicPlaces);
        return `overte://${url.hostname}${path}`;
    }
    // The native Places UI uses the directory's advertised IP+viewpoint. Resolve
    // only configured place names and match their current pinned authority.
    for (const name of publicPlaces) {
        const place = await resolve(name, publicPlaces);
        const native = new URL(place.nativeDomain);
        if (url.host === native.host) return `overte://${name}${path}`;
    }
    throw Error('This Places destination is not enabled by the gateway administrator. Choose an enabled domain in the browser.');
}
