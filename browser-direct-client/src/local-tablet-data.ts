// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type { BrowserIdentity } from './session-contract';

export function domainEndpoint(input: string): string {
    const value = input.trim();
    if (!value || value.length > 4096) throw Error('Enter the domain server address.');
    let url: URL;
    try { url = new URL(value); } catch { throw Error('Enter a complete domain server address.'); }
    if (!['http:', 'https:', 'ws:', 'wss:', 'overte:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.hash)
        throw Error('Use a domain server address without embedded credentials or a fragment.');
    return value;
}

export function browserIdentity(displayName: string, skeletonModelURL: string, scale: number): BrowserIdentity {
    const name = displayName.trim(), model = skeletonModelURL.trim();
    if (!name || name.length > 128 || /[\u0000-\u001f\u007f]/.test(name)) throw Error('Choose a display name of 1–128 characters.');
    if (!Number.isFinite(scale) || scale < 0.05 || scale > 20) throw Error('Choose an avatar scale between 0.05 and 20.');
    if (model.length > 4096) throw Error('The avatar model address is too long.');
    if (model && !/^(?:https?:|atp:|qrc:|resource:)/i.test(model)) throw Error('Use an HTTPS, HTTP or ATP avatar address.');
    if (model && /^(?:https?:)/i.test(model)) {
        let url: URL;
        try { url = new URL(model); } catch { throw Error('The avatar model address is invalid.'); }
        if (!url.hostname || url.username || url.password) throw Error('The avatar model address must not contain credentials.');
    }
    return { displayName: name, skeletonModelURL: model, scale };
}
