// SPDX-License-Identifier: Apache-2.0
/** Surface bounded same-origin gateway errors without consuming successful asset data. */
export async function requireAssetResponse(response:Response,label:string):Promise<void> {
    if (response.ok) return;
    let detail = '';
    if (response.headers.get('content-type')?.includes('application/json') && response.body) {
        const reader = response.body.getReader(), chunks:Uint8Array[] = [];
        let bytes = 0;
        try {
            while (true) {
                const part = await reader.read();
                if (part.done) break;
                bytes += part.value.length;
                if (bytes > 8192) { await reader.cancel(); break; }
                chunks.push(part.value);
            }
            if (bytes <= 8192) {
                const data = new Uint8Array(bytes); let offset = 0;
                for (const chunk of chunks) {data.set(chunk,offset);offset += chunk.length;}
                const value = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(data));
                if (typeof value?.error === 'string') detail = value.error.replace(/[\x00-\x1f\x7f]/g,' ').slice(0,512);
            }
        } catch { /* Preserve the HTTP status when the gateway error body is invalid. */ }
        finally { reader.releaseLock(); }
    }
    throw Error(`${label} request returned HTTP ${response.status}${detail ? `: ${detail}` : '.'}`);
}
