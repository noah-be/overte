// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import http from 'node:http';
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mkdtemp, mkdir, readFile, writeFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { WebSocketServer, WebSocket } from 'ws';
import { domainAddress, pose, validateNativePermissions, nativeDomainAddress, ASSET_SANDBOX_POLICY } from './validation.mjs';
import { readPolicyFile } from './permission-policy.mjs';
import { terminateProcess } from './process-lifecycle.mjs';

const run = promisify(execFile);
const directory = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.OVERTE_GATEWAY_PORT || 8090);
const host = process.env.OVERTE_GATEWAY_HOST || '127.0.0.1';
const domains = (process.env.OVERTE_GATEWAY_DOMAINS || 'overte://127.0.0.2:40102').split(',').map(domainAddress);
const assetOrigins = new Set((process.env.OVERTE_GATEWAY_ASSET_ORIGINS || '').split(',').filter(Boolean));
const origins = new Set((process.env.OVERTE_GATEWAY_ORIGINS || `http://127.0.0.1:${port},http://localhost:${port},http://127.0.0.1:5173,http://localhost:5173`).split(','));
const maximumSessions = Number(process.env.OVERTE_GATEWAY_MAX_SESSIONS || 4);
if (!Number.isSafeInteger(maximumSessions) || maximumSessions < 1) throw Error('OVERTE_GATEWAY_MAX_SESSIONS must be a positive safe integer.');
const sessions = new Map();
const sockets = new Set();
const send = (socket, value) => { if (socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 4 * 1024 * 1024) socket.send(JSON.stringify(value)); };
const cookie = request => /(?:^|;\s*)overte_browser=([a-f0-9]{64})(?:;|$)/.exec(request.headers.cookie || '')?.[1];
const json = (response, code, value) => { response.writeHead(code, { 'content-type': 'application/json', 'cache-control': 'no-store' }); response.end(JSON.stringify(value)); };
const equal = (a, b) => typeof a === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));

class Session {
    constructor(browser, owner) {
        this.id = randomUUID(); this.token = randomBytes(32).toString('hex'); this.browser = browser;
        this.owner = owner; this.modules = []; this.processes = []; this.pendingAssets = new Map();
        this.httpAssets = new Set();
        this.closed = false; this.muted = true; this.lastPose = 0;
    }
    async launch(message) {
        const domain = domainAddress(message.domain);
        if (!domains.includes(domain)) throw Error('This domain is not enabled by the gateway administrator.');
        if (!process.env.OVERTE_INTERFACE) throw Error('The gateway needs OVERTE_INTERFACE pointing to a matching native Overte Interface executable.');
        if (!process.env.OVERTE_GATEWAY_GUEST_POLICY) throw Error('The gateway requires a reviewed anonymous guest permission policy for this domain.');
        const permissionPolicies = await readPolicyFile(process.env.OVERTE_GATEWAY_GUEST_POLICY, domains);
        this.permissionPolicy = permissionPolicies.get(domain);
        if (!this.permissionPolicy) throw Error('This domain has no verified anonymous guest permission policy.');
        this.nativeDomain = await nativeDomainAddress(domain);
        this.domain = domain;
        this.directory = await mkdtemp(path.join(tmpdir(), 'overte-browser-'));
        if (this.closed) throw Error('Session cancelled.');
        await Promise.all(['config', 'data', 'cache'].map(name => mkdir(path.join(this.directory, name), { mode: 0o700 })));
        const label = this.id.replaceAll('-', '');
        this.input = `overte_browser_input_${label}`; this.output = `overte_browser_output_${label}`;
        this.pulseServer = `unix:${path.join(this.directory, 'pulse.socket')}`;
        const pulseScript = path.join(this.directory, 'audio.pa');
        await writeFile(pulseScript, `load-module module-native-protocol-unix socket=${path.join(this.directory, 'pulse.socket')} auth-anonymous=1\n`
            + `load-module module-null-sink sink_name=${this.input} rate=48000 channels=2\n`
            + `load-module module-null-sink sink_name=${this.output} rate=48000 channels=2\n`
            + `set-default-source ${this.input}.monitor\nset-default-sink ${this.output}\n`, { mode: 0o600 });
        const audioEnv = { ...process.env, PULSE_SERVER: this.pulseServer,
            XDG_CONFIG_HOME: path.join(this.directory, 'config'), XDG_RUNTIME_DIR: this.directory,
            DBUS_SESSION_BUS_ADDRESS: 'unix:path=/dev/null' };
        if (process.env.OVERTE_GATEWAY_PULSEAUDIO_LIBRARY_PATH) audioEnv.LD_LIBRARY_PATH = process.env.OVERTE_GATEWAY_PULSEAUDIO_LIBRARY_PATH;
        const pulseArgs = ['-n', '--daemonize=no', '--use-pid-file=no', '--exit-idle-time=-1', '--log-target=stderr', '-F', pulseScript];
        if (process.env.OVERTE_GATEWAY_PULSEAUDIO_MODULES) pulseArgs.push(`--dl-search-path=${process.env.OVERTE_GATEWAY_PULSEAUDIO_MODULES}`);
        this.audioServer = this.process(process.env.OVERTE_GATEWAY_PULSEAUDIO || 'pulseaudio', pulseArgs, audioEnv, 'Isolated audio server');
        let audioReady = false;
        for (let attempt = 0; attempt < 50 && !this.closed; attempt++) {
            try { await run('pactl', [`--server=${this.pulseServer}`, 'info'], { timeout: 1000 }); audioReady = true; break; }
            catch { await new Promise(resolve => setTimeout(resolve, 100)); }
        }
        if (!audioReady) throw Error('The isolated audio server could not start. Install PulseAudio and its null-sink modules.');
        const settingsDirectory = path.join(this.directory, 'config/Overte');
        await mkdir(settingsDirectory, { mode: 0o700 });
        await writeFile(path.join(settingsDirectory, 'Interface.json'), JSON.stringify({
            'Audio/Desktop/INPUT': `${this.input}.monitor`, 'Audio/Desktop/OUTPUT': this.output,
            'Audio/mutedDesktop': true, firstRun: false, viewportResolutionScale: 0.1,
        }), { mode: 0o600 });
        if (this.closed) return;
        const bridge = await readFile(path.join(directory, 'native-bridge.js'), 'utf8');
        const nativeDomain = process.env.OVERTE_GATEWAY_NATIVE_SCHEME === 'hifi' ? this.nativeDomain.replace(/^overte:/, 'hifi:') : this.nativeDomain;
        const configuration = { url: `ws://127.0.0.1:${port}/native`, token: this.token, domain: nativeDomain, radius: Number(process.env.OVERTE_GATEWAY_RADIUS || 512) };
        const script = path.join(this.directory, 'bridge.js');
        await writeFile(script, `var BROWSER_GATEWAY = ${JSON.stringify(configuration)};\n${bridge}`, { mode: 0o600 });
        const env = { ...process.env, XDG_CONFIG_HOME: path.join(this.directory, 'config'),
            XDG_DATA_HOME: path.join(this.directory, 'data'), XDG_CACHE_HOME: path.join(this.directory, 'cache'),
            PULSE_SERVER: this.pulseServer, PULSE_SOURCE: `${this.input}.monitor`, PULSE_SINK: this.output };
        env.QT_SCALE_FACTOR = process.env.OVERTE_GATEWAY_SCALE_FACTOR || '1';
        env.QT_AUTO_SCREEN_SCALE_FACTOR = '0';
        env.QT_ENABLE_HIGHDPI_SCALING = '0';
        if (process.env.OVERTE_INTERFACE_LIBRARY_PATH) env.LD_LIBRARY_PATH = process.env.OVERTE_INTERFACE_LIBRARY_PATH;
        if (process.env.OVERTE_GATEWAY_DISPLAY) env.DISPLAY = process.env.OVERTE_GATEWAY_DISPLAY;
        const args = ['--allowMultipleInstances', '--no-updater', '--no-launcher', '--no-login-suggestion',
            '--suppress-settings-reset', '--disableDisplayPlugins', 'OpenXR,OpenVR', '--cache', path.join(this.directory, 'cache'),
            '--defaultScriptsOverride', script, '--url', nativeDomain, '--displayName', String(message.displayName || 'Browser visitor').slice(0, 64)];
        this.nativeProcess = this.process(process.env.OVERTE_INTERFACE, args, env, 'Native Overte client');
        this.nativeProcess.once('exit', () => { if (!this.closed) { send(this.browser, { type: 'state', state: 'error', message: 'The native gateway client stopped.' }); this.close(false); } });
        this.capture = this.process('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-f', 'pulse', '-fragment_size', '3840', '-i', `${this.output}.monitor`,
            '-f', 's16le', '-ar', '48000', '-ac', '2', 'pipe:1'], env, 'Audio capture');
        let residual = Buffer.alloc(0);
        this.capture.stdout.on('data', chunk => {
            const data = residual.length ? Buffer.concat([residual, chunk]) : chunk;
            const length = data.length - data.length % 4;
            residual = data.subarray(length);
            if (length && !this.closed && this.permissionsApproved && this.connected && this.browser.readyState === WebSocket.OPEN && this.browser.bufferedAmount < 192000) this.browser.send(data.subarray(0, length), { binary: true });
        });
        this.playback = this.process('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-probesize', '32', '-analyzeduration', '0', '-f', 's16le', '-ar', '48000', '-ac', '1', '-i', 'pipe:0',
            '-f', 'pulse', '-device', this.input, 'Browser microphone'], env, 'Audio playback');
        this.playback.stdin.on('error', () => {});
        this.timeout = setTimeout(() => { if (!this.native) { send(this.browser, { type: 'state', state: 'error', message: 'The native gateway did not start its bridge within 90 seconds.' }); this.close(false); } }, 90000);
        send(this.browser, { type: 'state', state: 'connecting', sessionId: this.id, message: 'Starting your isolated native connection…' });
    }
    process(command, args, env, label) {
        const child = spawn(command, args, { env, stdio: ['pipe', 'pipe', 'pipe'] });
        this.processes.push(child);
        child.on('error', () => { send(this.browser, { type: 'state', state: 'error', message: `${label} could not be started.` }); this.close(false); });
        // Native logs may contain domain/account data; keep them private to this temporary session.
        if (label === 'Native Overte client') {
            let diagnostics = '';
            child.stdout.on('data', data => { diagnostics = (diagnostics + data).slice(-128 * 1024); });
            child.stderr.on('data', data => { diagnostics = (diagnostics + data).slice(-128 * 1024); });
            this.diagnostics = () => diagnostics;
        } else {
            child.stderr.on('data', () => {});
            child.once('exit', code => {
                if (!this.closed) { send(this.browser, { type: 'state', state: 'error', message: `${label} stopped. Leave and reconnect to restore voice.` }); this.close(false); }
            });
        }
        return child;
    }
    async asset(url) {
        if (!this.native || !this.permissionsApproved || !url.startsWith('atp:')) throw Error('Asset service is not connected.');
        if (this.pendingAssets.size >= 16) throw Error('Too many asset requests.');
        const requestId = randomUUID();
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => { this.pendingAssets.delete(requestId); reject(Error('The native asset request timed out.')); }, 30000);
            this.pendingAssets.set(requestId, { resolve, reject, timer });
            send(this.native, { type: 'asset', requestId, url });
        });
    }
    waitForDomain() {
        clearTimeout(this.connectionTimeout);
        this.connectionTimeout = setTimeout(() => {
            if (!this.connected && !this.closed) {
                send(this.browser, { type: 'state', state: 'error', message: 'The domain did not accept the connection within 45 seconds.' }); this.close(false);
            }
        }, 45000);
    }
    async close(notify = true) {
        if (this.closed) return;
        this.closed = true; this.permissionsApproved = false; this.connected = false; this.muted = true;
        clearTimeout(this.timeout); clearTimeout(this.connectionTimeout);
        if (this.launching) await this.launching.catch(() => {});
        for (const controller of this.httpAssets) controller.abort();
        this.httpAssets.clear();
        for (const pending of this.pendingAssets.values()) { clearTimeout(pending.timer); pending.reject(Error('Session ended.')); }
        this.pendingAssets.clear();
        if (this.native?.readyState === WebSocket.OPEN && this.nativeProcess?.exitCode === null) {
            await new Promise(resolve => {
                const finished = () => { clearTimeout(timer); this.nativeProcess.removeListener('exit', finished); resolve(); };
                const timer = setTimeout(finished, 3000);
                this.nativeProcess.once('exit', finished);
                send(this.native, { type: 'shutdown' });
            });
        }
        this.native?.close();
        await Promise.all(this.processes.map(child => terminateProcess(child)));
        sessions.delete(this.id);
        if (this.directory) await rm(this.directory, { recursive: true, force: true }).catch(() => {});
        if (notify) send(this.browser, { type: 'state', state: 'disconnected', message: 'You left the domain.' });
    }
}

const server = http.createServer(async (request, response) => {
    try {
        const url = new URL(request.url, `http://localhost:${port}`);
        if (url.pathname === '/api/config') return json(response, 200, { domains: domains.map(address => ({ address, name: new URL(address).hostname })), transport: 'native-gateway', audio: { sampleRate: 48000, inputChannels: 1, outputChannels: 2 } });
        if (url.pathname === '/api/session') {
            const token = cookie(request) || randomBytes(32).toString('hex');
            response.setHeader('set-cookie', `overte_browser=${token}; HttpOnly; SameSite=Strict; Path=/${request.headers['x-forwarded-proto'] === 'https' ? '; Secure' : ''}`);
            return json(response, 200, { ready: true });
        }
        if (url.pathname.startsWith('/api/assets/')) {
            const session = sessions.get(url.pathname.slice('/api/assets/'.length));
            if (!session || !session.permissionsApproved || !equal(cookie(request), session.owner)) return json(response, 403, { error: 'This asset belongs to another session or the session has ended.' });
            const asset = url.searchParams.get('url');
            if (!asset || asset.length > 4096) return json(response, 400, { error: 'Invalid asset address.' });
            let data, type = 'application/octet-stream';
            if (asset.startsWith('atp:')) data = await session.asset(asset);
            else {
                if (session.httpAssets.size >= 16) throw Error('Too many asset requests.');
                const controller = new AbortController(); session.httpAssets.add(controller);
                const abortClosedResponse = () => { if (!response.writableEnded) controller.abort(); };
                response.on('close', abortClosedResponse);
                try {
                const deadline = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
                let target = new URL(asset);
                for (let redirects = 0; redirects < 5; redirects++) {
                    if (!assetOrigins.has(target.origin) || target.username || target.password) throw Error('The asset origin is not enabled by the gateway administrator.');
                    const remote = await fetch(target, { redirect: 'manual', signal: deadline });
                    if ([301, 302, 303, 307, 308].includes(remote.status)) { target = new URL(remote.headers.get('location'), target); continue; }
                    if (!remote.ok) throw Error(`Asset server returned HTTP ${remote.status}.`);
                    type = remote.headers.get('content-type') || type;
                    if (Number(remote.headers.get('content-length')) > 32 * 1024 * 1024) throw Error('Asset exceeds the 32 MiB limit.');
                    const chunks = []; let size = 0;
                    for await (const chunk of remote.body) { size += chunk.length; if (size > 32 * 1024 * 1024) throw Error('Asset exceeds the 32 MiB limit.'); chunks.push(chunk); }
                    data = Buffer.concat(chunks); break;
                }
                if (!data) throw Error('Too many asset redirects.');
                } finally { session.httpAssets.delete(controller); response.off('close', abortClosedResponse); }
            }
            if (session.closed || !session.permissionsApproved) return json(response, 403, { error: 'The asset session ended before the response was ready.' });
            response.writeHead(200, { 'content-type': type, 'cache-control': 'private, no-store', 'x-content-type-options': 'nosniff', 'content-security-policy': ASSET_SANDBOX_POLICY }); response.end(data); return;
        }
        const distribution = path.resolve(directory, '../dist');
        let requested = path.resolve(distribution, `.${url.pathname}`);
        if (!requested.startsWith(`${distribution}${path.sep}`) && requested !== distribution) return json(response, 403, { error: 'Invalid path.' });
        if (url.pathname === '/') requested = path.join(distribution, 'index.html');
        const info = await stat(requested).catch(() => null);
        if (!info?.isFile()) return json(response, 404, { error: 'Build the browser frontend first with npm run build.' });
        const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
        response.writeHead(200, { 'content-type': types[path.extname(requested)] || 'application/octet-stream',
            'x-content-type-options': 'nosniff', 'referrer-policy': 'same-origin' }); response.end(await readFile(requested));
    } catch (error) { json(response, 502, { error: error.message }); }
});
const browserServer = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });
const nativeServer = new WebSocketServer({ noServer: true, maxPayload: 48 * 1024 * 1024 });
server.on('upgrade', (request, socket, head) => {
    if (sockets.size >= maximumSessions * 4) { socket.end('HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n'); return; }
    const endpoint = new URL(request.url, `http://localhost:${port}`).pathname;
    if (endpoint === '/native' && ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(request.socket.remoteAddress)) return nativeServer.handleUpgrade(request, socket, head, ws => nativeServer.emit('connection', ws, request));
    if (endpoint !== '/session' || !origins.has(request.headers.origin) || !cookie(request)) { socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return; }
    browserServer.handleUpgrade(request, socket, head, ws => browserServer.emit('connection', ws, request));
});
browserServer.on('connection', (browser, request) => {
    sockets.add(browser); let session; let joins = 0;
    browser.on('message', async (data, binary) => {
        try {
            if (binary) {
                if (session?.playback && !session.closed && session.connected && session.permissionsApproved && !session.muted && data.length % 2 === 0 && data.length <= 19200 && session.playback.stdin.writableLength < 19200) session.playback.stdin.write(data);
                return;
            }
            const message = JSON.parse(data.toString());
            if (message.type === 'join') {
                if (session && !session.closed) throw Error('Leave your current domain before joining another.');
                if (sessions.size >= maximumSessions || ++joins > 20) throw Error('The gateway session limit has been reached.');
                session = new Session(browser, cookie(request)); sessions.set(session.id, session);
                session.launching = session.launch(message);
                await session.launching;
            } else if (message.type === 'leave') { await session?.close(); }
            else if (session && !session.closed) {
                if (message.type === 'pose') { if (Date.now() - session.lastPose < 20) return; session.lastPose = Date.now(); send(session.native, pose(message)); }
                else if (message.type === 'mute' && typeof message.muted === 'boolean') { session.muted = message.muted; send(session.native, { type: 'mute', muted: message.muted }); }
                else if (message.type === 'interact' && typeof message.entityId === 'string' && /^\{?[a-f0-9-]{36}\}?$/i.test(message.entityId)) send(session.native, { type: 'interact', entityId: message.entityId });
            }
        } catch (error) { send(browser, { type: 'state', state: 'error', message: error.message }); if (session && !session.native) await session.close(false); }
    });
    browser.on('close', () => { sockets.delete(browser); session?.close(); });
    browser.on('error', () => {});
});
nativeServer.on('connection', native => {
    sockets.add(native); let session;
    const timer = setTimeout(() => { if (!session) native.close(); }, 5000);
    native.on('message', data => {
        try {
            const message = JSON.parse(data.toString());
            if (!session) {
                if (message.type !== 'nativeHello') return native.close();
                session = [...sessions.values()].find(candidate => equal(message.token, candidate.token));
                if (!session || session.native || session.closed) return native.close();
                session.native = native; session.lastNativeMessage = Date.now(); clearTimeout(timer); clearTimeout(session.timeout);
                session.waitForDomain();
                send(native, { type: 'mute', muted: session.muted }); return;
            }
            if (session.closed) return;
            session.lastNativeMessage = Date.now();
            if (message.type === 'heartbeat') return;
            if (message.type === 'permissions') {
                if (!Number.isSafeInteger(message.permissionRevision) || message.permissionRevision < 1) return native.close();
                try { validateNativePermissions(message.permissions, session.permissionPolicy.permissions, message.domain, session.nativeDomain); }
                catch (error) {
                    session.permissionsApproved = false;
                    send(session.browser, { type: 'state', state: 'error', message: error.message });
                    session.close(false); return;
                }
                session.permissionsApproved = true;
                send(native, { type: 'permissionsAccepted', permissionRevision: message.permissionRevision, muted: session.muted }); return;
            }
            if (!session.permissionsApproved && !(message.type === 'state' && message.state === 'error') && message.type !== 'warning') return;
            if (message.type === 'asset') {
                const pending = session.pendingAssets.get(message.requestId);
                if (!pending) return;
                clearTimeout(pending.timer); session.pendingAssets.delete(message.requestId);
                if (message.error) pending.reject(Error(String(message.error)));
                else if (typeof message.data !== 'string' || message.data.length > 44 * 1024 * 1024) pending.reject(Error('Invalid or oversized native asset.'));
                else {
                    const bytes = Buffer.from(message.data, 'base64');
                    if (bytes.length > 32 * 1024 * 1024) pending.reject(Error('Asset exceeds the 32 MiB limit.'));
                    else pending.resolve(bytes);
                }
            } else {
                if (message.type === 'entities') {
                    const hidden = message.entities.filter(entity => entity.type === 'Model' && !entity.modelURL).length;
                    if (hidden && !session.warnedAssetPermission) {
                        session.warnedAssetPermission = true;
                        send(session.browser, { type: 'warning', message: 'This domain does not expose model URLs to this visitor. Some models cannot be displayed; request asset URL viewing permission from the domain owner.' });
                    }
                }
                if (message.type === 'state' && message.state === 'connected') { session.connected = true; clearTimeout(session.connectionTimeout); }
                if (message.type === 'state' && message.state === 'connecting') { session.permissionsApproved = false; session.connected = false; session.waitForDomain(); }
                send(session.browser, { ...message, sessionId: session.id });
                if (message.type === 'state' && message.state === 'error') session.close(false);
            }
        } catch { native.close(); }
    });
    native.on('close', () => { clearTimeout(timer); sockets.delete(native); if (session && !session.closed) { send(session.browser, { type: 'state', state: 'error', message: 'The native domain bridge disconnected.' }); session.close(false); } });
    native.on('error', () => {});
});
const heartbeat = setInterval(() => {
    for (const session of sessions.values()) {
        if (session.native && Date.now() - session.lastNativeMessage > 60000) {
            send(session.browser, { type: 'state', state: 'error', message: 'The native bridge stopped responding. You can join again.' }); session.close(false);
        }
    }
    for (const socket of sockets) {
        if (socket.gatewayAlive === false) { socket.terminate(); continue; }
        socket.gatewayAlive = false; socket.ping();
    }
}, 30000);
let checkingPolicies = false;
const policyWatchdog = setInterval(async () => {
    if (checkingPolicies || !sessions.size) return;
    checkingPolicies = true;
    try {
        const policies = await readPolicyFile(process.env.OVERTE_GATEWAY_GUEST_POLICY, domains);
        for (const session of sessions.values()) {
            if (!session.permissionPolicy) continue;
            const current = policies.get(session.domain);
            if (!current || current.settingsFile !== session.permissionPolicy.settingsFile || JSON.stringify(current.permissions) !== JSON.stringify(session.permissionPolicy.permissions)) {
                session.permissionsApproved = false;
                send(session.browser, { type: 'state', state: 'error', message: 'The domain guest permission policy changed. Connection revoked; review the policy before reconnecting.' });
                session.close(false);
            }
        }
    } catch {
        for (const session of sessions.values()) {
            session.permissionsApproved = false;
            send(session.browser, { type: 'state', state: 'error', message: 'The domain guest permission policy is no longer valid. Connection revoked.' });
            session.close(false);
        }
    } finally { checkingPolicies = false; }
}, 10000);
for (const websocketServer of [browserServer, nativeServer]) websocketServer.on('connection', socket => {
    socket.gatewayAlive = true; socket.on('pong', () => { socket.gatewayAlive = true; });
});
server.listen(port, host, () => console.log(`Overte browser gateway: http://${host}:${port} (${domains.length} enabled domain(s))`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => {
    clearInterval(heartbeat);
    clearInterval(policyWatchdog);
    await Promise.all([...sessions.values()].map(session => session.close()));
    for (const socket of sockets) socket.terminate();
    server.close(() => process.exit(0));
});
