// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { approvedAssetAddress } from './validation.mjs';

export async function downloadAsset(address, configuredOrigins, cancellation) {
    const signal = AbortSignal.any([cancellation, AbortSignal.timeout(30000)]);
    let target = new URL(address);
    for (let redirects = 0; redirects < 5; redirects++) {
        // Redirect bodies are cancelled instead of consuming another response's
        // connection while fetching its destination. Every hop is allowlisted.
        const destination = approvedAssetAddress(target, configuredOrigins);
        const remote = await fetch(destination, { redirect: 'manual', signal });
        try {
            if ([301, 302, 303, 307, 308].includes(remote.status)) {
                const location = remote.headers.get('location');
                if (!location) throw Error('The asset redirect has no destination.');
                target = new URL(location, destination); continue;
            }
            if (!remote.ok) throw Error(`Asset server returned HTTP ${remote.status}.`);
            if (Number(remote.headers.get('content-length')) > 32 * 1024 * 1024) throw Error('Asset exceeds the 32 MiB limit.');
            const chunks = []; let size = 0;
            for await (const chunk of remote.body) {
                size += chunk.length;
                if (size > 32 * 1024 * 1024) throw Error('Asset exceeds the 32 MiB limit.');
                chunks.push(chunk);
            }
            return { data: Buffer.concat(chunks), type: remote.headers.get('content-type') || 'application/octet-stream' };
        } finally { await remote.body?.cancel().catch(() => {}); }
    }
    throw Error('Too many asset redirects.');
}
