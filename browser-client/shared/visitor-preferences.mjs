// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Shared browser/gateway validation. Preferences never authorize domain access.
const encoder = new TextEncoder();
const record = value => value && typeof value === 'object' && !Array.isArray(value);
export function viewpointPath(path) {
    if (!path || path === '/') return '';
    const parts = path.split('/');
    if (parts[0] !== '' || ![2, 3].includes(parts.length)) throw Error('Only a finite position and optional normalized orientation are supported in a place address.');
    const number = value => /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value) ? Number(value) : NaN;
    const position = parts[1].split(',').map(number);
    if (position.length !== 3 || position.some(value => !Number.isFinite(value) || Math.abs(value) >= 32768)) throw Error('Invalid place viewpoint position.');
    let result = '/' + position.join(',');
    if (parts.length === 3) {
        const orientation = parts[2].split(',').map(number);
        if (orientation.length !== 4 || orientation.some(value => !Number.isFinite(value) || Math.abs(value) > 1.01)
            || Math.abs(orientation.reduce((total, value) => total + value * value, 0) - 1) > 0.02) throw Error('Invalid place viewpoint orientation.');
        result += '/' + orientation.join(',');
    }
    return result;
}
export function visitorAddress(value) {
    if (typeof value !== 'string' || value.length < 1 || value.length > 1024 || /[\x00-\x20\x7f]/.test(value)) throw Error('Invalid visitor bookmark address.');
    const url = new URL(value.includes('://') ? value : `overte://${value}`);
    if (!['overte:', 'hifi:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash
        || !/^(?:[a-z0-9_.-]+|\[[0-9a-f:]+\])$/i.test(url.hostname)
        || (url.port && (!/^\d{1,5}$/.test(url.port) || Number(url.port) < 1 || Number(url.port) > 65535))) throw Error('Only safe Overte domain bookmark addresses are supported.');
    url.protocol = 'overte:'; url.hostname = url.hostname.toLowerCase(); url.pathname = viewpointPath(url.pathname);
    if (url.href.length > 1024) throw Error('Visitor bookmark address exceeds its limit.');
    return url.href;
}
export function validateVisitorPreferences(value = { bookmarks: [] }) {
    if (!record(value) || Object.keys(value).some(key => !['bookmarks', 'home'].includes(key))
        || !Array.isArray(value.bookmarks) || value.bookmarks.length > 100) throw Error('Visitor preferences require at most 100 bookmarks and an optional home address.');
    const names = new Set();
    const bookmarks = value.bookmarks.map(entry => {
        if (!record(entry) || Object.keys(entry).some(key => !['name', 'address'].includes(key)) || typeof entry.name !== 'string') throw Error('Invalid visitor bookmark.');
        const name = entry.name.trim();
        if (!name || name.length > 64 || encoder.encode(name).byteLength > 256 || /[\x00-\x1f\x7f]/.test(name) || names.has(name)) throw Error('Bookmark names must be unique nonempty text of at most 64 characters.');
        names.add(name); return { name, address: visitorAddress(entry.address) };
    });
    // Native LocationBookmarks reserves the exact name Home for its home entry.
    const homeBookmark = bookmarks.find(bookmark => bookmark.name === 'Home');
    const result = { bookmarks: bookmarks.filter(bookmark => bookmark.name !== 'Home') };
    if (value.home !== undefined) result.home = visitorAddress(value.home);
    else if (homeBookmark) result.home = homeBookmark.address;
    return result;
}
