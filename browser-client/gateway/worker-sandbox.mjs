// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { randomBytes, randomInt } from 'node:crypto';
import {realpathSync} from 'node:fs';
import { access, stat, lstat, writeFile, mkdir } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';

const run = promisify(execFile);
const displays = new Set();
const runtimeVariables = ['LD_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QTWEBENGINEPROCESS_PATH',
    'QT_SCALE_FACTOR', 'QT_AUTO_SCREEN_SCALE_FACTOR', 'QT_ENABLE_HIGHDPI_SCALING',
    'OVERTE_PUBLIC_NATIVE_ROOT', 'LIBGL_ALWAYS_SOFTWARE', 'QT_QUICK_BACKEND'];

export function workerEnvironment(directory, source = {}) {
    const env = { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8', HOME: directory, USER: 'browser', LOGNAME: 'browser',
        TMPDIR: path.join(directory, 'tmp'), XDG_CONFIG_HOME: path.join(directory, 'config'),
        XDG_DATA_HOME: path.join(directory, 'data'), XDG_CACHE_HOME: path.join(directory, 'cache'),
        XDG_RUNTIME_DIR: directory, DBUS_SESSION_BUS_ADDRESS: 'unix:path=/dev/null' };
    for (const key of runtimeVariables) if (typeof source[key] === 'string') env[key] = source[key];
    for (const key of ['PULSE_SERVER', 'PULSE_SOURCE', 'PULSE_SINK']) if (typeof source[key] === 'string') env[key] = source[key];
    return env;
}

const inside = (filename, root) => filename === root || filename.startsWith(root + path.sep);
function reviewedRoot(value) {
    const resolved = path.resolve(value);
    const forbidden = filename => ['/', '/home', '/root', '/tmp', '/run', '/etc', '/proc', '/dev', process.env.HOME].includes(filename)
        || /\/(?:\.ssh|\.gnupg|\.config|\.local|\.cache)(?:\/|$)/.test(filename);
    // An administrator-supplied package alias must not turn a narrow-looking
    // runtime path into a bind of the operator's home or private configuration.
    // Keep the original guest path so legitimate installed-library aliases work.
    if (!path.isAbsolute(value) || forbidden(resolved) || forbidden(realpathSync(resolved))) {
        throw Error('Native runtime mounts must identify installed packages, not operator profiles or broad host directories.');
    }
    return resolved;
}

/** Produce the inner filesystem/PID boundary; the network owner may wrap it. */
export async function sandboxCommand({ directory, executable, env, roots = [], display, readOnlyOverrides = [] }) {
    const command = process.env.OVERTE_GATEWAY_BWRAP || 'bwrap';
    const args = ['--unshare-user', '--uid', String(process.getuid?.() || 1000),
        '--gid', String(process.getgid?.() || 1000), '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent',
        '--new-session', '--clearenv', '--ro-bind', '/usr', '/usr'];
    for (const [source, target] of [['/lib', '/lib'], ['/lib64', '/lib64'], ['/bin', '/bin']]) {
        try { await access(source); args.push('--ro-bind', source, target); } catch { /* Distribution-dependent paths. */ }
    }
    args.push('--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/tmp/.X11-unix', '--dir', '/etc');
    for (const source of ['/etc/ld.so.cache', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf',
        '/etc/ssl', '/etc/pki', '/etc/fonts', '/etc/ca-certificates',
        // Fedora's NSS trust module follows this system-managed alternatives link.
        // Bind its resolved library at the exact link target without exposing /etc.
        '/etc/alternatives/libnssckbi.so.x86_64', '/etc/alternatives/libnssckbi.so']) {
        try { await access(source); args.push('--ro-bind', source, source); } catch { /* Optional system trust/font paths. */ }
    }
    const mounted = [];
    for (const value of [...roots, executable]) {
        const source = reviewedRoot(value);
        if (inside(source, '/usr') || mounted.some(root => inside(source, root))) continue;
        const info = await stat(source);
        if (!info.isDirectory() && !info.isFile()) throw Error('Native runtime mounts must be regular package files or directories.');
        args.push('--ro-bind', source, source); mounted.push(source);
    }
    args.push('--bind', directory, directory, '--ro-bind', path.join(directory, 'machine-id'), '/etc/machine-id');
    for (const override of readOnlyOverrides) {
        const source = path.resolve(override.source), target = path.resolve(override.target);
        if (!inside(source, path.resolve(directory)) || !((path.basename(source) === 'browser-snapshot.js' && target.endsWith('/scripts/system/snapshot.js'))
                || (path.basename(source) === 'browser-places.js' && target.endsWith('/scripts/system/places/places.js'))
                || (path.basename(source) === 'browser-places-ui.js' && target.endsWith('/scripts/system/places/placesHtml.js'))) || !roots.some(root => inside(target, reviewedRoot(root)))) {
            throw Error('Only reviewed session Snapshot and Places adapters may override installed native scripts.');
        }
        const [sourceInfo, targetInfo] = await Promise.all([lstat(source), lstat(target)]);
        if (!sourceInfo.isFile() || sourceInfo.isSymbolicLink() || !targetInfo.isFile() || targetInfo.isSymbolicLink()) {
            throw Error('Native snapshot adapters must bind regular trusted script files.');
        }
        args.push('--ro-bind', source, target);
    }
    if (display !== undefined) args.push('--ro-bind', `/tmp/.X11-unix/X${display}`, `/tmp/.X11-unix/X${display}`);
    args.push('--chdir', directory);
    for (const [key, value] of Object.entries(env)) args.push('--setenv', key, value);
    args.push('--', executable);
    return { command, args, env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } };
}

export async function prepareWorker({ directory, executable, sourceEnvironment, nativeRoot, spawnOwned, signal, readOnlyOverrides = [] }) {
    const env = workerEnvironment(directory, sourceEnvironment);
    await mkdir(path.join(directory, 'tmp'), { recursive: true, mode: 0o700 });
    const roots = [reviewedRoot(nativeRoot || path.dirname(executable))];
    for (const key of ['LD_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH']) {
        for (const value of (env[key] || '').split(':').filter(Boolean)) roots.push(reviewedRoot(value));
    }
    if (env.QTWEBENGINEPROCESS_PATH) roots.push(reviewedRoot(path.dirname(env.QTWEBENGINEPROCESS_PATH)));
    if (env.OVERTE_PUBLIC_NATIVE_ROOT) roots.push(reviewedRoot(env.OVERTE_PUBLIC_NATIVE_ROOT));
    await writeFile(path.join(directory, 'machine-id'), randomBytes(16).toString('hex') + '\n', { mode: 0o600 });
    await writeFile(path.join(directory, 'Xauthority'), '', { mode: 0o600 });
    let display;
    for (let attempts = 0; attempts < 100; attempts++) {
        const candidate = randomInt(1200, 60000);
        if (displays.has(candidate)) continue;
        try { await access(`/tmp/.X11-unix/X${candidate}`); continue; } catch { /* Free socket name. */ }
        try { await access(`/tmp/.X${candidate}-lock`); continue; } catch { /* Free display lock. */ }
        display = candidate; displays.add(display); break;
    }
    if (display === undefined) throw Error('No isolated display could be reserved.');
    try {
        const authority = path.join(directory, 'Xauthority');
        await run('xauth', ['-f', authority, 'add', `:${display}`, 'MIT-MAGIC-COOKIE-1', randomBytes(16).toString('hex')],
            { env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8', HOME: directory }, timeout: 5000 });
        if (signal.aborted) throw Error('Session cancelled.');
        const xvfb = spawnOwned(process.env.OVERTE_GATEWAY_XVFB || 'Xvfb', ['-screen', '0', '1024x768x24',
            '-nolisten', 'tcp', '-noreset', '-auth', authority, `:${display}`],
            { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8', HOME: directory, TMPDIR: directory }, 'Isolated display');
        let ready = false;
        for (let attempts = 0; attempts < 100 && !signal.aborted; attempts++) {
            if (xvfb.exitCode !== null || xvfb.signalCode !== null) break;
            try { await access(`/tmp/.X11-unix/X${display}`); ready = true; break; }
            catch { await new Promise(resolve => setTimeout(resolve, 50)); }
        }
        if (signal.aborted) throw Error('Session cancelled.');
        if (!ready) throw Error('The private Xvfb display could not start. Install Xvfb and xauth.');
        env.DISPLAY = `:${display}`; env.XAUTHORITY = authority;
        env.LIBGL_ALWAYS_SOFTWARE = '1';
        const result = await sandboxCommand({ directory, executable, env, roots, display, readOnlyOverrides });
        return { ...result, display, release: () => displays.delete(display) };
    } catch (error) { displays.delete(display); throw error; }
}
