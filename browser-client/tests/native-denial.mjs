// SPDX-License-Identifier: Apache-2.0
// Actual native server refusal test, separate from the gateway's earlier policy refusal.
// The entire fixture owns an IPC namespace, including native Interface's shared-memory port reader.
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir, mkdtemp, readFile, writeFile, open } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { once } from 'node:events';
import http from 'node:http';
import { WebSocketServer } from 'ws';
import { PERMISSION_KEYS } from '../gateway/permission-policy.mjs';
import { nativeAdminCredential } from '../lab/native-admin.mjs';

if (process.env.OVERTE_DENIAL_PRIVATE_IPC !== '1') {
    const isolated = spawn('unshare', ['--user', '--map-current-user', '--ipc', '--', process.execPath, fileURLToPath(import.meta.url)], {
        env: { ...process.env, OVERTE_DENIAL_PRIVATE_IPC: '1', QTWEBENGINE_DISABLE_SANDBOX: '1' }, stdio: 'inherit',
    });
    isolated.on('error', () => { console.error('The refusal fixture requires unshare with user/IPC namespaces.'); process.exitCode = 1; });
    const [code] = await once(isolated, 'exit'); process.exit(code ?? 1);
}

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const lab = path.join(repo, 'build/browser-lab');
const directory = await mkdtemp(path.join(lab, 'native-denial-'));
const processes = [], handles = [];
const observer = http.createServer();
const websocketServer = new WebSocketServer({ server: observer });
const token = randomBytes(32).toString('hex');
const administratorCredential = nativeAdminCredential();
const administratorAuthorization = 'Basic ' + Buffer.from(`browser-denial:${administratorCredential.token}`).toString('base64');
const base = { ...process.env, QT_QPA_PLATFORM: 'xcb', DISPLAY: ':94', QT_SCALE_FACTOR: '1', QT_AUTO_SCREEN_SCALE_FACTOR: '0',
    XDG_CONFIG_HOME: path.join(directory, 'config'), XDG_DATA_HOME: path.join(directory, 'data'), XDG_CACHE_HOME: path.join(directory, 'cache') };
async function processFor(label, executable, args, env) {
    const log = await open(path.join(directory, `${label}.log`), 'w', 0o600); handles.push(log);
    const child = spawn(executable, args, { env, cwd: repo, stdio: ['ignore', log.fd, log.fd] });
    processes.push(child); child.on('error', () => {}); return child;
}
async function administrationStatus(authorization) {
    return new Promise((resolve, reject) => {
        const request = http.get('http://127.0.0.1:45300/settings.json', {
            headers: authorization ? { Authorization: authorization } : {},
        }, response => { response.resume(); response.on('end', () => resolve(response.statusCode)); });
        request.on('error', reject); request.setTimeout(500, () => request.destroy(Error('Administration request timed out.')));
    });
}
let timer;
try {
    for (const name of ['config', 'data', 'cache']) await mkdir(path.join(directory, name), { mode: 0o700 });
    await new Promise((resolve, reject) => { observer.once('error', reject); observer.listen(45310, '127.0.0.1', resolve); });
    const deny = Object.fromEntries(PERMISSION_KEYS.map(key => [key, false]));
    const settings = { version: 2.7, metaverse: { local_port: 45302, automatic_networking: 'disabled', enable_packet_verification: true },
        security: { http_username: 'browser-denial', http_password: administratorCredential.nativeVerifier, standard_permissions: ['anonymous', 'localhost', 'logged-in', 'friends'].map(permissions_id => ({ permissions_id, ...deny })),
            ip_permissions: [], machine_fingerprint_permissions: [], allowed_subnets: ['127.0.0.0/8'] }, wizard: { completed: true } };
    const settingsFile = path.join(directory, 'domain.json'); await writeFile(settingsFile, JSON.stringify(settings), { mode: 0o600 });
    const serverDirectory = path.join(lab, 'server/opt/overte');
    await processFor('domain', path.join(serverDirectory, 'domain-server'), [ '--user-config', settingsFile, '--logOptions', 'nocolor,nojournald'], {
        ...base, LD_LIBRARY_PATH: `${serverDirectory}/lib:${lab}/appimage/squashfs-root/usr/lib`,
        HIFI_DOMAIN_SERVER_HTTP_PORT: '45300', HIFI_DOMAIN_SERVER_HTTPS_PORT: '45301', HIFI_DOMAIN_SERVER_PORT: '45302', HIFI_DOMAIN_SERVER_DTLS_PORT: '45303',
    });
    let serverReady = false;
    for (let attempt = 0; attempt < 50; attempt++) {
        try { const status = await administrationStatus(administratorAuthorization);
            if (status === 200) { serverReady = true; break; } }
        catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    assert(serverReady, 'Isolated denied domain must start');
    const unauthenticated = await administrationStatus();
    assert([401, 403].includes(unauthenticated), 'The denied-domain HTTP administration must require authentication');
    const socket = path.join(directory, 'pulse.socket');
    const pulseFile = path.join(directory, 'audio.pa');
    await writeFile(pulseFile, `load-module module-native-protocol-unix socket=${socket} auth-anonymous=1\nload-module module-null-sink sink_name=denied_input\nload-module module-null-sink sink_name=denied_output\nset-default-source denied_input.monitor\nset-default-sink denied_output\n`, { mode: 0o600 });
    await processFor('pulse', path.join(repo, 'browser-client/lab/pulseaudio-local.sh'), ['-n', '--daemonize=no', '--use-pid-file=no', '--exit-idle-time=-1', '-F', pulseFile], {
        ...base, DBUS_SESSION_BUS_ADDRESS: 'unix:path=/dev/null', XDG_RUNTIME_DIR: directory,
    });
    const nativeConfig = path.join(directory, 'config/Overte'); await mkdir(nativeConfig);
    await writeFile(path.join(nativeConfig, 'Interface.json'), JSON.stringify({ 'Audio/mutedDesktop': true,
        'Audio/Desktop/INPUT': 'denied_input.monitor', 'Audio/Desktop/OUTPUT': 'denied_output', firstRun: false, viewportResolutionScale: 0.1 }), { mode: 0o600 });
    const script = path.join(directory, 'bridge.js');
    await writeFile(script, `var BROWSER_GATEWAY = ${JSON.stringify({ url: 'ws://127.0.0.1:45310/native', token, domain: 'hifi://127.0.0.1:45302' })};\n`
        + await readFile(path.join(repo, 'browser-client/gateway/native-bridge.js'), 'utf8'), { mode: 0o600 });
    const refusal = new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(Error('Native permission refusal was not observed within 45 seconds.')), 45000);
        websocketServer.on('connection', ws => {
            let authenticated = false;
            ws.on('message', data => {
                const value = JSON.parse(data);
                if (!authenticated) { assert.equal(value.type, 'nativeHello'); assert.equal(value.token, token); authenticated = true; return; }
                if (value.type === 'state' && value.state === 'error') resolve(value.message);
                if (value.type === 'entities' || value.type === 'avatars') reject(Error('Denied domain exposed world data.'));
            });
        });
    });
    await processFor('native', path.join(lab, 'appimage/squashfs-root/AppRun'), ['--allowMultipleInstances', '--no-updater', '--no-launcher', '--no-login-suggestion',
        '--suppress-settings-reset', '--disableDisplayPlugins', 'OpenXR,OpenVR', '--defaultScriptsOverride', script, '--url', 'hifi://127.0.0.1:45302', '--displayName', 'Native permission denial test'],
    { ...base, PULSE_SERVER: `unix:${socket}` });
    const reason = await refusal; clearTimeout(timer);
    assert.match(reason, /authoriz|permission|connect/i);
    const result = { test: 'native-domain-permission-refusal', result: 'passed', protocolArtifacts: 'Overte 2026.04.1 client and server',
        at: new Date().toISOString(), domain: 'hifi://127.0.0.1:45302', reason, worldDataExposed: false, administrationRequiresAuthentication: true,
        authorizedAdministrationStatus: 200, unauthenticatedAdministrationStatus: unauthenticated, domainIpcIsolated: true };
    await mkdir(path.join(repo, 'browser-client/test-results'), { recursive: true });
    await writeFile(path.join(repo, 'browser-client/test-results/native-denial.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
} finally {
    clearTimeout(timer);
    for (const child of processes.reverse()) {
        if (child.exitCode !== null) continue;
        const exited = once(child, 'exit'); child.kill('SIGTERM');
        await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 1500))]);
        if (child.exitCode === null) child.kill('SIGKILL');
    }
    for (const client of websocketServer.clients) client.terminate();
    await new Promise(resolve => observer.close(resolve));
    await Promise.all(handles.map(handle => handle.close()));
}
