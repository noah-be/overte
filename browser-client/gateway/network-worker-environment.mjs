// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Recover the native --setenv contract, never the host launcher's environment.
// The immutable owner still validates every option, key, value and path.
export function networkWorkerEnvironment(args) {
    if (!Array.isArray(args) || args.length > 512 || args.some(value => typeof value !== 'string')) {
        throw Error('Native environment arguments refused');
    }
    const end = args.indexOf('--');
    if (end < 0) throw Error('Native environment delimiter refused');
    const environment = Object.create(null);
    for (let index = 0; index < end; index++) {
        if (args[index] !== '--setenv') continue;
        if (index + 2 >= end) throw Error('Native environment pair refused');
        const key = args[++index], value = args[++index];
        if (!/^[A-Z][A-Z0-9_]{0,127}$/.test(key) || Object.hasOwn(environment, key)
                || value.length > 8192 || value.includes('\0')) throw Error('Native environment pair refused');
        environment[key] = value;
    }
    return { ...environment };
}
