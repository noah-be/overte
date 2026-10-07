// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, realpath, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { sandboxCommand } from './worker-sandbox.mjs';
import { networkWorkerEnvironment } from './network-worker-environment.mjs';

test('actual sandbox launch distinguishes PATH-only native settings from host PATH and LANG', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-environment-contract-'));
    try {
        const native = { PATH: '/usr/bin:/bin' };
        const worker = await sandboxCommand({ directory, executable: await realpath('/usr/bin/python3'), env: native });
        assert.deepEqual(networkWorkerEnvironment(worker.args), native);
        assert.notDeepEqual(worker.env, native);
        assert.deepEqual(worker.env, { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' });
        assert.deepEqual(networkWorkerEnvironment([...worker.args, '-c', '--setenv PRIVATE injected']), native);
    } finally { await rm(directory, { recursive: true, force: true }); }
});

test('native loader settings remain explicit while duplicates, partial pairs and malformed keys are refused', () => {
    assert.deepEqual(networkWorkerEnvironment(['--setenv', 'LD_LIBRARY_PATH', '/reviewed/native/lib', '--', '/reviewed/native']),
        { LD_LIBRARY_PATH: '/reviewed/native/lib' });
    for (const args of [[], ['--setenv', 'PATH', '--'], ['--setenv', '__proto__', 'injected', '--'],
        ['--setenv', 'PATH', 'first', '--setenv', 'PATH', 'second', '--'], ['--setenv', 'PATH', 'private\0secret', '--']]) {
        assert.throws(() => networkWorkerEnvironment(args), /refused/);
    }
});

test('actual immutable admission rejects the old launcher environment and admits the declared native one', async () => {
    const directory = await mkdtemp('/tmp/overte-browser-envproof-');
    try {
        await writeFile(path.join(directory, 'machine-id'), 'a'.repeat(32) + '\n');
        await writeFile(path.join(directory, 'network-resolv.conf'), 'nameserver 10.0.2.3\n');
        const executable = await realpath('/usr/bin/python3');
        const worker = await sandboxCommand({ directory, executable, env: { PATH: '/usr/bin:/bin' } });
        const args = [...worker.args];
        args[args.indexOf('/etc/resolv.conf')] = path.join(directory, 'network-resolv.conf');
        const uid = process.getuid(), gid = process.getgid();
        const config = { command: worker.command, args, environment: worker.env,
            bridgePort: 40999, bridgeSocket: path.join(directory, 'native-network.socket'), supervisorParentPID: 42 };
        const policy = { version: 1, hostUID: uid, hostGID: gid, sessionParent: '/tmp',
            nativeExecutables: [executable], nativeReadRoots: [path.dirname(executable)] };
        const attestation = { version: 1, hostUID: uid, hostGID: gid, parentPID: 42, userNS: [1, 2], netNS: [1, 3], routes: 12 };
        const source = fileURLToPath(new URL('../tools/trusted-network/src/owner_admission.py', import.meta.url));
        const code = 'import importlib.util,json,sys\n' +
            's=importlib.util.spec_from_file_location("owned_admission",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n' +
            'c,p,a=json.load(sys.stdin)\n' +
            'try:m.validate(c,p,a,filesystem=False)\n' +
            'except m.Refusal as e:sys.exit(3 if e.args==("worker-executable",) else 4)\n';
        const check = () => spawnSync('/usr/bin/python3', ['-B', '-c', code, source],
            { input: JSON.stringify([config, policy, attestation]), encoding: 'utf8', timeout: 5000 });
        assert.equal(check().status, 3, 'Original host/native mismatch must fail actual admission');
        config.environment = networkWorkerEnvironment(args);
        const admitted = check();
        assert.equal(admitted.status, 0, 'Declared native environment must pass all actual admission checks');
        assert.equal(admitted.stderr, '');
    } finally { await rm(directory, { recursive: true, force: true }); }
});
