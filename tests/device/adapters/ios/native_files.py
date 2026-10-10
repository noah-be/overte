"""Read a bounded live AFC file without relying on an earlier path size."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0


async def read_file(files, path, limit, eof_status=None):
    if type(limit) is not int or limit <= 0:
        raise ValueError('native file bound must be a positive integer')
    handle = await files.fopen(path)
    if not handle:
        raise RuntimeError('native result file did not open')
    result = bytearray()
    try:
        while len(result) <= limit:
            requested = min(256 * 1024, limit + 1 - len(result))
            try:
                chunk = await files.fread(handle, requested)
            except Exception as error:
                if eof_status is None or getattr(error, 'status', None) != eof_status:
                    raise
                break
            if not isinstance(chunk, bytes) or len(chunk) > requested:
                raise RuntimeError('native file read returned invalid bytes')
            result.extend(chunk)
            if len(result) > limit:
                raise RuntimeError('native result exceeds its byte bound')
            if len(chunk) < requested:
                break
    finally:
        await files.fclose(handle)
    return bytes(result)
