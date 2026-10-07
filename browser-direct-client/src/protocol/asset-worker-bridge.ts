// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
type AssetFetchEvent = { data: unknown; ports: readonly MessagePort[] };
type AssetGetter = (path: string, generation: string) => Promise<ArrayBuffer>;
export interface AssetFetchLifecycle {
    isCurrent(): boolean;
    onSettled(): void;
}

/** Reply only to the requesting worker port. In-flight asset bytes may be
 * shared by several fetches, so each port must receive an owned structured
 * clone rather than detaching the shared native result through a transfer. */
export function answerAssetFetch(event: AssetFetchEvent, getAsset: AssetGetter, lifecycle?: AssetFetchLifecycle): boolean {
    const request = event.data as { type?: string; path?: string; generation?: string } | null;
    if (request?.type !== 'overte-atp-fetch' || !event.ports[0]
        || typeof request.path !== 'string' || typeof request.generation !== 'string') return false;
    const port = event.ports[0], { path, generation } = request;
    void Promise.resolve().then(() => {
        if (lifecycle && !lifecycle.isCurrent()) throw new Error('The ATP session has ended.');
        return getAsset(path, generation);
    }).then(
        data => {
            if (!lifecycle || lifecycle.isCurrent()) port.postMessage({ data });
        },
        error => {
            if (!lifecycle || lifecycle.isCurrent()) {
                port.postMessage({ error: error instanceof Error ? error.message : 'The ATP asset is unavailable.' });
            }
        },
    ).finally(() => { try { port.close(); } finally { lifecycle?.onSettled(); } }).catch(() => {});
    return true;
}
