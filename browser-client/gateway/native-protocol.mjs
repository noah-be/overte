// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { spawn } from 'node:child_process';
import { readFile, stat } from 'node:fs/promises';
import { terminateProcess } from './process-lifecycle.mjs';

export async function inspectNativeProtocol({ executable, args, env, filename, ownedProcesses, signal,
    timeoutMilliseconds = 20000, terminationGrace = 3000 }) {
    if (signal.aborted) throw Error('Session cancelled.');
    const child = spawn(executable, args, { env, stdio: 'ignore' });
    ownedProcesses.push(child);
    let reason;
    await new Promise((resolve, reject) => {
        const stop = message => {
            reason = message;
            terminateProcess(child, terminationGrace).catch(reject);
        };
        const abort = () => stop('Session cancelled.');
        const timer = setTimeout(() => stop('Native protocol inspection timed out.'), timeoutMilliseconds);
        const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); };
        child.once('error', () => { cleanup(); reject(Error('Native protocol inspection could not start.')); });
        child.once('exit', code => {
            cleanup();
            if (reason || code !== 0) reject(Error(reason || 'Native protocol inspection failed.'));
            else resolve();
        });
        signal.addEventListener('abort', abort, { once: true });
        if (signal.aborted) abort();
    });
    if (signal.aborted) throw Error('Session cancelled.');
    if ((await stat(filename)).size > 64) throw Error('Native protocol signature file is invalid.');
    const signature = (await readFile(filename, 'utf8')).trim();
    if (!/^[A-Za-z0-9+/]{22}==$/.test(signature)) throw Error('Native protocol signature file is invalid.');
    return signature;
}
