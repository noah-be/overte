// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0

/** Domain signaling URL validation shared by the page and native worker. */
export function normalizeEndpoint(endpoint: string, pageURL?: string): string {
    let value = endpoint.trim();
    if (!value.includes('://')) value = `wss://${value}`;
    const url = new URL(value);
    if (url.username || url.password || url.search || url.hash) throw new Error('Use a domain signaling URL without credentials or query parameters.');
    if (url.protocol === 'http:') url.protocol = 'ws:';
    if (url.protocol === 'https:') url.protocol = 'wss:';
    if (!['ws:', 'wss:'].includes(url.protocol)) throw new Error('Enter the domain server’s ws:// or wss:// browser endpoint.');
    const protocol = pageURL ? new URL(pageURL).protocol : globalThis.location?.protocol;
    if (url.protocol === 'ws:' && protocol === 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
        throw new Error('This secure page requires a secure wss:// domain endpoint.');
    }
    return url.toString();
}
