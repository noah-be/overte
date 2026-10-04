// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { MAX_VISITOR_FILE_BYTES } from './tablet-files.mjs';

/** Cookie ownership is checked by the caller; no browser-provided filesystem path is accepted. */
export async function serveVisitorFiles(request, response, url, session, originAllowed) {
    const json = (code, value) => {
        if (!response.headersSent && !response.destroyed) {
            response.writeHead(code, { 'content-type': 'application/json', 'cache-control': 'no-store',
                'x-content-type-options': 'nosniff' });
            response.end(JSON.stringify(value));
        }
    };
    const active = () => session && !session.closed && session.permissionsApproved && session.connected && session.files;
    if (!active()) return json(403, { error: 'The visitor files session has ended or is unavailable.' });
    if (!['GET', 'PUT', 'DELETE'].includes(request.method)) return json(405, { error: 'Unsupported visitor files method.' });
    if ((request.method !== 'GET' || request.headers.origin) && !originAllowed(request.headers.origin)) {
        return json(403, { error: 'Visitor file requests must originate from this browser client.' });
    }
    const name = url.searchParams.get('name');
    try {
        if (request.method === 'GET' && name === null) {
            const files = await session.files.list();
            return active() ? json(200, { files }) : json(403, { error: 'The visitor files session has ended.' });
        }
        if (name === null) return json(400, { error: 'A plain visitor file name is required.' });
        if (request.method === 'PUT') {
            const length = request.headers['content-length'];
            if (length !== undefined && (!/^\d+$/.test(length) || Number(length) > MAX_VISITOR_FILE_BYTES)) {
                return json(413, { error: 'Visitor upload exceeds the file limit.' });
            }
            const file = await session.files.upload(name, request);
            return active() ? json(200, file) : json(403, { error: 'The visitor files session has ended.' });
        }
        if (request.method === 'DELETE') {
            await session.files.delete(name);
            return active() ? json(200, { deleted: true }) : json(403, { error: 'The visitor files session has ended.' });
        }
        const file = await session.files.download(name);
        if (!active()) { file.stream.destroy(); return json(403, { error: 'The visitor files session has ended.' }); }
        const stop = () => file.stream.destroy();
        response.once('close', stop);
        file.stream.once('error', () => response.destroy());
        file.stream.once('close', () => response.off('close', stop));
        response.writeHead(200, file.headers); file.stream.pipe(response);
    } catch (error) {
        if (response.headersSent) response.destroy();
        else json(error.code === 'ENOENT' ? 404 : 400, { error: 'The visitor file operation failed. Check the name, file size and workspace limit.' });
    }
}
