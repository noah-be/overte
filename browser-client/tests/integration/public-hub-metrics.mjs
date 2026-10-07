// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Aggregate only: URLs, visitor identifiers and credentials never enter output.
export const ASSET_CATEGORIES = ['FBX', 'FST', 'texmeta', 'JSON', 'image', 'other'];
export function assetCategory(address) {
    try {
        const pathname = decodeURIComponent(new URL(address).pathname).toLowerCase();
        if (/\.fbx$/.test(pathname)) return 'FBX';
        if (/\.fst$/.test(pathname)) return 'FST';
        // Native texture metadata has this exact suffix; other JSON is separate.
        if (/\.texmeta\.json$/.test(pathname)) return 'texmeta';
        if (/\.json$/.test(pathname)) return 'JSON';
        if (/\.(?:png|jpe?g|webp|gif|bmp|tga|dds|ktx2?|psd|exr|hdr|avif|svg|tiff?)$/.test(pathname)) return 'image';
    } catch {}
    return 'other';
}
export function assetCategoryTotals(entries) {
    const totals = Object.fromEntries(ASSET_CATEGORIES.map(category => [category, {
        uniqueURLs: 0, requests: 0, duplicateRequests: 0, knownBytes: 0, unknownByteResponses: 0,
        sources: { download: 0, shared: 0, memory: 0, unknown: 0 },
    }]));
    for (const entry of entries) {
        const result = ASSET_CATEGORIES.includes(entry.category) ? totals[entry.category] : totals.other;
        result.uniqueURLs++; result.requests += entry.requests;
        result.duplicateRequests += Math.max(0, entry.requests - 1);
        result.knownBytes += entry.knownBytes; result.unknownByteResponses += entry.unknownByteResponses;
        for (const source of Object.keys(result.sources)) result.sources[source] += entry.sources?.[source] || 0;
    }
    return totals;
}

export function assetTransferTotals(entries) {
    const safe = entries.map(entry => ({
        urlSHA256: entry.urlSHA256,
        category: ASSET_CATEGORIES.includes(entry.category) ? entry.category : 'other',
        requests: entry.requests, knownBytes: entry.knownBytes,
        unknownByteResponses: entry.unknownByteResponses,
        totalMs: entry.totalMs, maximumMs: entry.maximumMs,
        sources: Object.fromEntries(['download','shared','memory','unknown'].map(source => [source,entry.sources?.[source] || 0])),
    }));
    return {
        uniqueURLs: safe.length,
        requests: safe.reduce((sum,entry) => sum + entry.requests,0),
        duplicateRequests: safe.reduce((sum,entry) => sum + Math.max(0,entry.requests-1),0),
        knownBytes: safe.reduce((sum,entry) => sum + entry.knownBytes,0),
        unknownByteResponses: safe.reduce((sum,entry) => sum + entry.unknownByteResponses,0),
        totalRequestMs: safe.reduce((sum,entry) => sum + entry.totalMs,0),
        maximumRequestMs: safe.reduce((maximum,entry) => Math.max(maximum,entry.maximumMs),0),
        sources: Object.fromEntries(['download','shared','memory','unknown'].map(source => [source,safe.reduce((sum,entry) => sum+entry.sources[source],0)])),
        categories: assetCategoryTotals(safe), entries: safe,
    };
}
export function assetSessionTotals(entries) {
    const sessions = new Map();
    for (const entry of entries) {
        if (!Number.isSafeInteger(entry.ordinal) || entry.ordinal < 1) throw Error('Invalid diagnostic session ordinal.');
        if (!sessions.has(entry.ordinal)) sessions.set(entry.ordinal,[]);
        sessions.get(entry.ordinal).push(entry);
    }
    return [...sessions].sort(([a],[b])=>a-b).map(([ordinal,items]) => ({ordinal,...assetTransferTotals(items)}));
}

export function requireWorldLoadingReady(sample) {
    if (!sample || !Number.isSafeInteger(sample.loadedModels) || sample.loadedModels < 1 ||
        sample.queuedModels !== 0 || sample.loadingModels !== 0 || sample.compilingGraphics !== 0) {
        throw Error('World model loading did not finish before its existing deadline.');
    }
}
