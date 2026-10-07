// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {writeFile,rename,rm} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';

/** An HTTP reader must see one complete command, including while its old
 * inode remains open. Only the caller's owned test directory is written. */
export async function writeAtomicFixtureCommand(filename,command) {
    if (!command || typeof command !== 'object' || Array.isArray(command)) throw Error('Invalid fixture command');
    const bytes=JSON.stringify(command)+'\n';
    if (Buffer.byteLength(bytes)>65536) throw Error('Fixture command exceeds its byte bound');
    const temporary=filename+'.'+randomUUID()+'.tmp';
    try {
        await writeFile(temporary,bytes,{flag:'wx',mode:0o600});
        await rename(temporary,filename);
    } finally {
        await rm(temporary,{force:true});
    }
}
