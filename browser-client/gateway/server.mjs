// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import http from 'node:http';
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mkdtemp, mkdir, readFile, writeFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { WebSocketServer, WebSocket } from 'ws';
import { domainAddress, pose, nativePoseRequest, validateNativePermissions, nativeDomainAddress, managedUDPDomain, ASSET_SANDBOX_POLICY, approvedAssetAddress } from './validation.mjs';
import { readPolicyFile } from './permission-policy.mjs';
import { terminateProcess, SharedTeardown } from './process-lifecycle.mjs';
import { publicPlaceNames, publicPlaceSelection, resolvePublicPlace, validatePublicPermissions, viewpointPath } from './public-places.mjs';
import { inspectNativeProtocol } from './native-protocol.mjs';
import { prepareTablet, TabletSession } from './tablet.mjs';
import { prepareWorker } from './worker-sandbox.mjs';
import { launchNativeNetwork } from './network-sandbox.mjs';
import { createVisitorFiles } from './tablet-files.mjs';
import { serveVisitorFiles } from './tablet-files-http.mjs';
import { NativeHeartbeat } from './socket-heartbeat.mjs';
import { managedNavigationSelection, validateNativeNavigation, admittedNavigationTarget } from './navigation.mjs';
import { preparePlacesOverride } from './places-override.mjs';
import { validateVisitorPreferences } from '../shared/visitor-preferences.mjs';
import { validateVisitorPersona, WEARABLE_FIELDS } from '../shared/visitor-persona.mjs';
import { prepareVisitorPersona, acceptedNativePersona } from './visitor-persona.mjs';
import { SessionAssets } from './session-assets.mjs';
import { downloadAsset } from './asset-download.mjs';

const run = promisify(execFile);
const directory = path.dirname(fileURLToPath(import.meta.url));
// Every session belongs to this server version, including during development edits.
// Restart the gateway when changing the native/browser protocol.
const nativeBridgeSource = (await readFile(path.join(directory, 'native-visitor-persona.js'), 'utf8')) + '\n'
    + (await readFile(path.join(directory, 'native-visitor-preferences.js'), 'utf8')) + '\n'
    + (await readFile(path.join(directory, 'native-world.js'), 'utf8')) + '\n'
    + await readFile(path.join(directory, 'native-bridge.js'), 'utf8');
const port = Number(process.env.OVERTE_GATEWAY_PORT || 8090);
const host = process.env.OVERTE_GATEWAY_HOST || '127.0.0.1';
const domains = (process.env.OVERTE_GATEWAY_DOMAINS || 'overte://127.0.0.2:40102').split(',').map(domainAddress);
const publicPlaces = publicPlaceNames(process.env.OVERTE_GATEWAY_PUBLIC_PLACES);
const assetOrigins = new Set((process.env.OVERTE_GATEWAY_ASSET_ORIGINS || '').split(',').filter(Boolean));
const publicAssetOrigins = new Set((process.env.OVERTE_GATEWAY_PUBLIC_ASSET_ORIGINS || '').split(',').filter(Boolean));
const origins = new Set((process.env.OVERTE_GATEWAY_ORIGINS || `http://127.0.0.1:${port},http://localhost:${port},http://127.0.0.1:5173,http://localhost:5173`).split(','));
const maximumSessions = Number(process.env.OVERTE_GATEWAY_MAX_SESSIONS || 4);
if (!Number.isSafeInteger(maximumSessions) || maximumSessions < 1) throw Error('OVERTE_GATEWAY_MAX_SESSIONS must be a positive safe integer.');
const sessions = new Map();
const sockets = new Set();
let shuttingDown = false;
let shutdownPromise;
const send = (socket, value) => { if (socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 4 * 1024 * 1024) socket.send(JSON.stringify(value)); };
const cookie = request => /(?:^|;\s*)overte_browser=([a-f0-9]{64})(?:;|$)/.exec(request.headers.cookie || '')?.[1];
const json = (response, code, value) => { response.writeHead(code, { 'content-type': 'application/json', 'cache-control': 'no-store' }); response.end(JSON.stringify(value)); };
const equal = (a, b) => typeof a === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));

class Session extends SharedTeardown {
    constructor(browser, owner, isCurrent = () => true) {
        super();
        this.id = randomUUID(); this.token = randomBytes(32).toString('hex'); this.browser = browser;
        this.owner = owner; this.modules = []; this.processes = []; this.pendingAssets = new Map();
        this.isCurrent = isCurrent;
        this.httpAssets = new Set();
        this.closed = false; this.muted = true; this.lastPose = 0;
    }
    async launch(message) {
        const preferences = validateVisitorPreferences(message.visitorPreferences);
        const persona = validateVisitorPersona(message.visitorPersona);
        const visitorDisplayName = validateVisitorPersona({displayName:Object.hasOwn(message,'displayName') ? message.displayName : persona.displayName ?? 'Browser visitor'}).displayName;
        const domain = domainAddress(message.domain);
        const managedSelection = managedNavigationSelection(domain, domains);
        if (managedSelection) {
            if (!process.env.OVERTE_INTERFACE) throw Error('The gateway needs OVERTE_INTERFACE pointing to a matching native Overte Interface executable.');
            if (!process.env.OVERTE_GATEWAY_GUEST_POLICY) throw Error('The gateway requires a reviewed anonymous guest permission policy for this domain.');
            const permissionPolicies = await readPolicyFile(process.env.OVERTE_GATEWAY_GUEST_POLICY, domains);
            this.policyDomain = managedSelection.configuredDomain;
            this.permissionPolicy = permissionPolicies.get(this.policyDomain);
            if (!this.permissionPolicy) throw Error('This domain has no verified anonymous guest permission policy.');
            this.nativeDomain = await nativeDomainAddress(managedSelection.domain);
            if (process.env.OVERTE_GATEWAY_WORKER_ISOLATION !== 'off') {
                this.managedUDP = managedUDPDomain(this.nativeDomain, process.env.OVERTE_GATEWAY_MANAGED_UDP_PORTS);
            }
        } else {
            const name = publicPlaceSelection(domain, publicPlaces);
            this.publicPlace = await resolvePublicPlace(name, publicPlaces);
            this.nativeDomain = this.publicPlace.nativeDomain;
            const requestedViewpoint = viewpointPath(new URL(domain).pathname);
            if (requestedViewpoint) { const pinned = new URL(this.nativeDomain); pinned.pathname = requestedViewpoint; this.nativeDomain = pinned.href; }
        }
        this.interfaceExecutable = this.publicPlace ? process.env.OVERTE_GATEWAY_PUBLIC_INTERFACE || process.env.OVERTE_INTERFACE : process.env.OVERTE_INTERFACE;
        if (!this.interfaceExecutable) throw Error('The gateway needs OVERTE_INTERFACE pointing to a matching native Overte Interface executable.');
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
        const bridge = nativeBridgeSource;
        const nativeDomain = process.env.OVERTE_GATEWAY_NATIVE_SCHEME === 'hifi' ? this.nativeDomain.replace(/^overte:/, 'hifi:') : this.nativeDomain;
        this.personaOrigins = this.publicPlace ? publicAssetOrigins : assetOrigins;
        const initialPersona = acceptedNativePersona(persona, this.personaOrigins);
        for (const warning of initialPersona.warnings) send(this.browser,{type:'warning',message:warning});
        const preservedPersonaFields = Object.keys(persona).filter(key => !Object.hasOwn(initialPersona.persona,key));
        const visitorPersona = await prepareVisitorPersona(this.directory, initialPersona.persona, this.personaOrigins,
            (this.publicPlace ? process.env.OVERTE_GATEWAY_PUBLIC_NATIVE_ORGANIZATION : process.env.OVERTE_GATEWAY_NATIVE_ORGANIZATION) || 'Overte');
        if (this.closed) throw Error('Session cancelled.');
        const configuration = { url: `ws://127.0.0.1:${port}/native`, token: this.token, domain: nativeDomain, radius: Number(process.env.OVERTE_GATEWAY_RADIUS || 512), visitorPreferences: preferences, visitorPersona: visitorPersona, visitorDisplayName, personaPreserveFields: preservedPersonaFields, wearableFields: WEARABLE_FIELDS,
            personaRuntimeFields: ['id','created','age','ageAsText','lastEdited','lastEditedBy','lastUpdated','lastSimulated','queryAACube','simulationOwner','entityHostType','owningAvatarID','renderInfo','boundingBox','position','rotation','parentID','localRotationAngles','jointRotations','jointTranslations'],
            personaInertFields: {script:'',serverScripts:'',scriptTimestamp:0,href:'',description:'',actionData:'',certificateID:'',itemName:'',itemDescription:'',itemCategories:'',itemArtist:'',itemLicense:'',marketplaceID:'',limitedRun:0,editionNumber:0,cloneable:false,cloneLifetime:300,cloneLimit:0,cloneDynamic:false,cloneAvatarEntity:false} };
        const defaultScripts = this.publicPlace ? process.env.OVERTE_GATEWAY_PUBLIC_DEFAULT_SCRIPTS || process.env.OVERTE_GATEWAY_DEFAULT_SCRIPTS : process.env.OVERTE_GATEWAY_DEFAULT_SCRIPTS;
        if (defaultScripts) {
            if (!defaultScripts.startsWith('file:') && !path.isAbsolute(defaultScripts)) throw Error('Default tablet scripts must be an absolute installed file path.');
            this.files = await createVisitorFiles(this.directory);
            configuration.tablet = await prepareTablet(this.directory, { defaultScriptsURL: defaultScripts.startsWith('file:') ? defaultScripts : pathToFileURL(defaultScripts).href,
                filesDirectory: this.files.directory });
            configuration.navigation = { channel: 'browser-places-' + randomUUID() };
            this.placesOverrides = await preparePlacesOverride(this.directory, {
                defaultScriptsURL: configuration.tablet.defaultScriptsURL, channel: configuration.navigation.channel, homeDomain: domain });
            this.tablet = new TabletSession({ framePath: configuration.tablet.framePath,
                filesDirectory: this.files.directory,
                sendNative: message => send(this.native, message), sendBrowser: message => send(this.browser, message),
                isActive: () => !this.closed && this.permissionsApproved && this.connected,
                getRevision: () => this.permissionRevision });
        }
        const script = path.join(this.directory, 'bridge.js');
        await writeFile(script, `var BROWSER_GATEWAY = ${JSON.stringify(configuration)};\n${bridge}`, { mode: 0o600 });
        if (this.closed) throw Error('Session cancelled.');
        const env = { ...process.env, XDG_CONFIG_HOME: path.join(this.directory, 'config'),
            XDG_DATA_HOME: path.join(this.directory, 'data'), XDG_CACHE_HOME: path.join(this.directory, 'cache'),
            PULSE_SERVER: this.pulseServer, PULSE_SOURCE: `${this.input}.monitor`, PULSE_SINK: this.output };
        env.QT_SCALE_FACTOR = process.env.OVERTE_GATEWAY_SCALE_FACTOR || '1';
        env.QT_AUTO_SCREEN_SCALE_FACTOR = '0';
        env.QT_ENABLE_HIGHDPI_SCALING = '0';
        if (process.env.OVERTE_INTERFACE_LIBRARY_PATH) env.LD_LIBRARY_PATH = process.env.OVERTE_INTERFACE_LIBRARY_PATH;
        if (this.publicPlace && process.env.OVERTE_GATEWAY_PUBLIC_INTERFACE_LIBRARY_PATH) env.LD_LIBRARY_PATH = process.env.OVERTE_GATEWAY_PUBLIC_INTERFACE_LIBRARY_PATH;
        if (process.env.OVERTE_GATEWAY_DISPLAY) env.DISPLAY = process.env.OVERTE_GATEWAY_DISPLAY;
        let launchCommand = this.interfaceExecutable, launchPrefix = [], launchEnv = env;
        if (process.env.OVERTE_GATEWAY_WORKER_ISOLATION === 'off') {
            if (this.publicPlace || this.tablet) throw Error('Public places and Tablet applications require native worker isolation.');
        } else {
            this.workerAbort = new AbortController();
            const nativeRoot = this.publicPlace ? process.env.OVERTE_GATEWAY_PUBLIC_NATIVE_ROOT || process.env.OVERTE_PUBLIC_NATIVE_ROOT || process.env.OVERTE_GATEWAY_NATIVE_ROOT : process.env.OVERTE_GATEWAY_NATIVE_ROOT;
            this.worker = await prepareWorker({ directory: this.directory, executable: this.interfaceExecutable,
                sourceEnvironment: env, nativeRoot, signal: this.workerAbort.signal,
                readOnlyOverrides: [...(configuration.tablet?.snapshotOverride ? [configuration.tablet.snapshotOverride] : []), ...(this.placesOverrides || [])],
                spawnOwned: (command, args, processEnv, label) => this.process(command, args, processEnv, label) });
            launchCommand = this.worker.command; launchPrefix = this.worker.args; launchEnv = this.worker.env;
            if (this.closed) throw Error('Session cancelled.');
        }
        if (this.publicPlace) {
            const protocolFile = path.join(this.directory, 'protocol.txt');
            this.protocolInspection = new AbortController();
            const signature = await inspectNativeProtocol({ executable: launchCommand,
                args: [...launchPrefix, '--allowMultipleInstances', '--no-updater', '--no-login-suggestion', '--suppress-settings-reset',
                    '--disableDisplayPlugins', 'OpenXR,OpenVR', '--protocolVersion', protocolFile], env: launchEnv, filename: protocolFile,
                ownedProcesses: this.processes, signal: this.protocolInspection.signal });
            if (signature !== this.publicPlace.protocolVersion) throw Error('The installed native client protocol does not match this public place. Install a matching Interface version.');
            if (this.closed) throw Error('Session cancelled.');
            send(this.browser, { type: 'warning', message: 'Public guest connection: this domain sees the gateway network address and machine identity. Account-required and source-identity-specific access are unsupported.' });
        }
        const args = ['--allowMultipleInstances', '--no-updater', '--no-launcher', '--no-login-suggestion',
            '--suppress-settings-reset', '--disableDisplayPlugins', 'OpenXR,OpenVR', '--cache', path.join(this.directory, 'cache'),
            '--defaultScriptsOverride', script, '--url', nativeDomain, '--displayName', visitorDisplayName || 'Browser visitor'];
        if (this.worker) {
            this.network = await launchNativeNetwork({ directory: this.directory, command: launchCommand,
                args: [...launchPrefix, ...args], env: launchEnv, hostPort: port, nativePath: '/native',
                spawnOwned: (command, arguments_, processEnv, label) => this.process(command, arguments_, processEnv, label),
                signal: this.workerAbort.signal, slirpExecutable: process.env.OVERTE_GATEWAY_SLIRP || 'slirp4netns',
                ...(this.managedUDP ? { managedUDP: this.managedUDP } : {}) });
            this.nativeProcess = this.network.child;
        } else this.nativeProcess = this.process(launchCommand, [...launchPrefix, ...args], launchEnv, 'Native Overte client');
        if (this.closed) throw Error('Session cancelled.');
        this.nativeProcess.once('exit', () => { if (!this.closed) { send(this.browser, { type: 'state', state: 'error', message: 'The native gateway client stopped.' }); this.close(false); } });
        // Native packages bundle Qt/OpenSSL libraries that may be incompatible
        // with host FFmpeg. Only Interface receives the native library environment.
        const mediaEnv = { ...process.env, PULSE_SERVER: this.pulseServer,
            PULSE_SOURCE: `${this.input}.monitor`, PULSE_SINK: this.output };
        delete mediaEnv.LD_LIBRARY_PATH;
        this.capture = this.process('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-f', 'pulse', '-fragment_size', '3840', '-i', `${this.output}.monitor`,
            '-f', 's16le', '-ar', '48000', '-ac', '2', 'pipe:1'], mediaEnv, 'Audio capture');
        let residual = Buffer.alloc(0);
        this.capture.stdout.on('data', chunk => {
            const data = residual.length ? Buffer.concat([residual, chunk]) : chunk;
            const length = data.length - data.length % 4;
            residual = data.subarray(length);
            if (length && !this.closed && this.permissionsApproved && this.connected && this.browser.readyState === WebSocket.OPEN && this.browser.bufferedAmount < 192000) this.browser.send(data.subarray(0, length), { binary: true });
        });
        this.playback = this.process('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-probesize', '32', '-analyzeduration', '0', '-f', 's16le', '-ar', '48000', '-ac', '1', '-i', 'pipe:0',
            '-f', 'pulse', '-device', this.input, 'Browser microphone'], mediaEnv, 'Audio playback');
        this.playback.stdin.on('error', () => {});
        this.timeout = setTimeout(() => { if (!this.native) { send(this.browser, { type: 'state', state: 'error', message: 'The native gateway did not start its bridge within 90 seconds.' }); this.close(false); } }, 90000);
        send(this.browser, { type: 'state', state: 'connecting', sessionId: this.id, message: 'Starting your isolated native connection…' });
    }
    process(command, args, env, label) {
        const child = spawn(command, args, { env, stdio: ['pipe', 'pipe', 'pipe'] });
        this.processes.push(child);
        child.on('error', () => { if (!this.closed) send(this.browser, { type: 'state', state: 'error', message: `${label} could not be started.` }); this.close(false); });
        // Native logs may contain domain/account data; keep them private to this temporary session.
        if (label === 'Native Overte client' || label === 'Private native network') {
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
    assetResponse(url, signal) {
        const configuredOrigins = this.publicPlace ? publicAssetOrigins : assetOrigins;
        // Revalidate even a byte-cache hit against the actual operator origin set.
        const address = url.startsWith('atp:') ? url : approvedAssetAddress(url, configuredOrigins).href;
        this.assets ??= new SessionAssets({
            authority: () => !this.closed && this.permissionsApproved ? `${this.permissionRevision}|${this.nativeDomain}` : null,
            load: async (target, cancellation) => target.startsWith('atp:')
                ? { data: await this.asset(target), type: 'application/octet-stream' }
                : downloadAsset(target, configuredOrigins, cancellation),
        });
        return this.assets.request(address, signal);
    }
    waitForDomain() {
        clearTimeout(this.connectionTimeout);
        this.connectionTimeout = setTimeout(() => {
            if (!this.connected && !this.closed) {
                send(this.browser, { type: 'state', state: 'error', message: 'The domain did not accept the connection within 45 seconds.' }); this.close(false);
            }
        }, 45000);
    }
    revoke() {
        this.closed = true; this.permissionsApproved = false; this.connected = false; this.muted = true;
        this.assets?.close();
        this.protocolInspection?.abort();
        this.workerAbort?.abort();
        this.tablet?.close();
        void this.files?.close();
        clearTimeout(this.timeout); clearTimeout(this.connectionTimeout); clearTimeout(this.navigationTimeout);
    }
    async teardown(notify = true) {
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
        // The native audio thread must finish while its PulseAudio server and X display still exist.
        if (this.nativeProcess) await terminateProcess(this.nativeProcess);
        await Promise.all(this.processes.filter(child => child !== this.nativeProcess && child !== this.audioServer).map(child => terminateProcess(child)));
        if (this.audioServer) await terminateProcess(this.audioServer);
        await this.files?.close();
        await this.network?.release();
        this.worker?.release();
        sessions.delete(this.id);
        if (this.directory) await rm(this.directory, { recursive: true, force: true }).catch(() => {});
        if (notify && this.isCurrent()) send(this.browser, { type: 'state', state: 'disconnected', message: 'You left the domain.' });
    }
}

const server = http.createServer(async (request, response) => {
    try {
        if (shuttingDown) return json(response, 503, { error: 'The gateway is shutting down.' });
        const url = new URL(request.url, `http://localhost:${port}`);
        if (url.pathname === '/api/config') return json(response, 200, { domains: [
            ...domains.map(address => ({ address, name: new URL(address).hostname, mode: 'anonymous-baseline' })),
            ...publicPlaces.map(name => ({ address: `overte://${name}`, name, mode: 'public-native-guest' })),
        ], transport: 'native-gateway', audio: { sampleRate: 48000, inputChannels: 1, outputChannels: 2 } });
        if (url.pathname === '/api/session') {
            const token = cookie(request) || randomBytes(32).toString('hex');
            response.setHeader('set-cookie', `overte_browser=${token}; HttpOnly; SameSite=Strict; Path=/${request.headers['x-forwarded-proto'] === 'https' ? '; Secure' : ''}`);
            return json(response, 200, { ready: true });
        }
        if (url.pathname.startsWith('/api/tablet-files/')) {
            const session = sessions.get(url.pathname.slice('/api/tablet-files/'.length));
            if (!session || !equal(cookie(request), session.owner)) return json(response, 403, { error: 'These visitor files belong to another session or the session has ended.' });
            return await serveVisitorFiles(request, response, url, session, origin => origins.has(origin));
        }
        if (url.pathname.startsWith('/api/assets/')) {
            const session = sessions.get(url.pathname.slice('/api/assets/'.length));
            if (!session || !session.permissionsApproved || !equal(cookie(request), session.owner)) return json(response, 403, { error: 'This asset belongs to another session or the session has ended.' });
            const asset = url.searchParams.get('url');
            if (!asset || asset.length > 4096) return json(response, 400, { error: 'Invalid asset address.' });
            const revision = session.permissionRevision;
            const reader = new AbortController();
            const abortClosedResponse = () => { if (!response.writableEnded) reader.abort(); };
            response.on('close', abortClosedResponse);
            let result;
            try { result = await session.assetResponse(asset, reader.signal); }
            finally { response.off('close', abortClosedResponse); }
            if (response.destroyed) return;
            if (session.closed || !session.permissionsApproved || session.permissionRevision !== revision || !equal(cookie(request), session.owner)) {
                return json(response, 403, { error: 'The asset session ended before the response was ready.' });
            }
            const { data, type } = result;
            response.writeHead(200, { 'content-type': type, 'content-length': data.length, 'x-overte-asset-source': result.source, 'cache-control': 'private, no-store', 'x-content-type-options': 'nosniff', 'content-security-policy': ASSET_SANDBOX_POLICY }); response.end(data); return;
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
// Allowed clipboard quotation, tabs and newlines may double the JSON size;
// text-field validators separately reject unsupported C0/NUL/DEL controls.
const browserServer = new WebSocketServer({ noServer: true, maxPayload: 192 * 1024 });
const nativeServer = new WebSocketServer({ noServer: true, maxPayload: 48 * 1024 * 1024 });
server.on('upgrade', (request, socket, head) => {
    if (shuttingDown || sockets.size >= maximumSessions * 4) { socket.end('HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n'); return; }
    const endpoint = new URL(request.url, `http://localhost:${port}`).pathname;
    if (endpoint === '/native' && ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(request.socket.remoteAddress)) return nativeServer.handleUpgrade(request, socket, head, ws => nativeServer.emit('connection', ws, request));
    if (endpoint !== '/session' || !origins.has(request.headers.origin) || !cookie(request)) { socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return; }
    browserServer.handleUpgrade(request, socket, head, ws => browserServer.emit('connection', ws, request));
});
browserServer.on('connection', (browser, request) => {
    sockets.add(browser); let session; let joins = 0; let pendingJoin = null;
    browser.on('message', async (data, binary) => {
        let attempt; let admission;
        try {
            if (binary) {
                if (session?.playback && !session.closed && session.connected && session.permissionsApproved && !session.muted && data.length % 2 === 0 && data.length <= 19200 && session.playback.stdin.writableLength < 19200) session.playback.stdin.write(data);
                return;
            }
            const message = JSON.parse(data.toString());
            if (message.type === 'join') {
                if (shuttingDown) throw Error('The gateway is shutting down.');
                if (pendingJoin || (session && !session.closed)) throw Error('Leave your current domain before joining another.');
                if (++joins > 20) throw Error('The gateway session limit has been reached.');
                const owner = cookie(request);
                admission = {}; pendingJoin = admission;
                if (sessions.size >= maximumSessions) {
                    const closing = [...sessions.values()].filter(candidate => candidate.closed && equal(candidate.owner, owner));
                    if (!closing.length) throw Error('The gateway session limit has been reached.');
                    send(browser, { type: 'state', state: 'connecting', message: 'Waiting for your previous connection to close…' });
                    await Promise.all(closing.map(candidate => candidate.close(false)));
                    if (pendingJoin !== admission || browser.readyState !== WebSocket.OPEN) throw Error('Join cancelled.');
                    if (shuttingDown) throw Error('The gateway is shutting down.');
                }
                if (pendingJoin !== admission || browser.readyState !== WebSocket.OPEN) throw Error('Join cancelled.');
                if (shuttingDown) throw Error('The gateway is shutting down.');
                if (sessions.size >= maximumSessions) throw Error('The gateway session limit has been reached.');
                pendingJoin = null;
                attempt = new Session(browser, owner, () => session === attempt);
                session = attempt; sessions.set(attempt.id, attempt);
                attempt.launching = attempt.launch(message);
                await attempt.launching;
            } else if (message.type === 'leave') { pendingJoin = null; await session?.close(); }
            else if (session && !session.closed) {
                if (message.type === 'pose') { if (session.pendingNativePose || Date.now() - session.lastPose < 20) return; session.lastPose = Date.now(); send(session.native, pose(message)); }
                else if (message.type === 'poseAccepted') {
                    if (!session.connected || !session.permissionsApproved || !session.pendingNativePose ||
                        message.nonce !== session.pendingNativePose.nonce || message.permissionRevision !== session.permissionRevision) return;
                    session.pendingNativePose = null;
                    clearTimeout(session.navigationTimeout);
                    send(session.native, { type: 'poseAccepted', nonce: message.nonce, permissionRevision: message.permissionRevision });
                }
                else if (message.type === 'navigationHistoryState') {
                    if (!session.connected || !session.permissionsApproved || message.permissionRevision !== session.permissionRevision
                        || typeof message.canGoBack !== 'boolean' || typeof message.canGoForward !== 'boolean') return;
                    send(session.native, { type: 'navigationHistoryState', permissionRevision: session.permissionRevision,
                        canGoBack: message.canGoBack, canGoForward: message.canGoForward });
                }
                else if (message.type === 'tablet') {
                    try {
                        if (!session.tablet) throw Error('This gateway worker has no configured installed tablet scripts.');
                        session.tablet.receive(message);
                    } catch (error) {
                        send(browser, { type: 'warning', message: error.message });
                    }
                }
                else if (message.type === 'mute' && typeof message.muted === 'boolean') { session.muted = message.muted; send(session.native, { type: 'mute', muted: message.muted }); }
                else if (message.type === 'interact' && typeof message.entityId === 'string' && /^\{?[a-f0-9-]{36}\}?$/i.test(message.entityId)) send(session.native, { type: 'interact', entityId: message.entityId });
            }
        } catch (error) {
            if ((!admission || attempt || pendingJoin === admission) && (!attempt || (attempt === session && !attempt.closed))) send(browser, { type: 'state', state: 'error', message: error.message });
            if (attempt && !attempt.native) await attempt.close(false);
        } finally { if (pendingJoin === admission) pendingJoin = null; }
    });
    browser.on('close', () => { pendingJoin = null; sockets.delete(browser); session?.close(); });
    browser.on('error', () => {});
});
nativeServer.on('connection', native => {
    sockets.add(native); let session;
    const timer = setTimeout(() => { if (!session) native.close(); }, 5000);
    native.on('message', async data => {
        let messageKind = 'message';
        try {
            const message = JSON.parse(data.toString());
            if (['poseRequest', 'entities', 'entityUpdates', 'avatars', 'state', 'permissions', 'asset', 'tablet'].includes(message.type)) messageKind = message.type;
            if (!session) {
                if (message.type !== 'nativeHello') return native.close();
                const candidate = [...sessions.values()].find(candidate => equal(message.token, candidate.token));
                if (!candidate || candidate.native || candidate.closed) return native.close();
                session = candidate;
                native.nativeHeartbeat = new NativeHeartbeat({ send: message => send(native, message) });
                session.native = native; session.lastNativeMessage = Date.now(); clearTimeout(timer); clearTimeout(session.timeout);
                session.waitForDomain();
                send(native, { type: 'mute', muted: session.muted }); return;
            }
            if (session.closed) return;
            if (message.type === 'nativePong') { native.nativeHeartbeat.receive(message); return; }
            session.lastNativeMessage = Date.now();
            if (message.type === 'heartbeat') return;
            if (message.type === 'permissions') {
                if (!Number.isSafeInteger(message.permissionRevision) || message.permissionRevision < 1) return native.close();
                try {
                    if (session.publicPlace) validatePublicPermissions(message.permissions, message.domain, session.nativeDomain, message.domainId, session.publicPlace);
                    else validateNativePermissions(message.permissions, session.permissionPolicy.permissions, message.domain, session.nativeDomain);
                }
                catch (error) {
                    session.permissionsApproved = false;
                    send(session.browser, { type: 'state', state: 'error', message: error.message });
                    session.close(false); return;
                }
                session.permissionsApproved = true;
                session.pendingNativePose = null;
                clearTimeout(session.navigationTimeout);
                if (session.permissionRevision !== message.permissionRevision) session.assets?.reset();
                session.permissionRevision = message.permissionRevision;
                send(native, { type: 'permissionsAccepted', permissionRevision: message.permissionRevision, muted: session.muted }); return;
            }
            if (!session.permissionsApproved && !(message.type === 'state' && message.state === 'error') && message.type !== 'warning') return;
            if (message.type === 'visitorPersona') {
                if (!session.connected || message.permissionRevision !== session.permissionRevision) return;
                const {persona,warnings} = acceptedNativePersona(message, session.personaOrigins);
                if(Object.keys(persona).length) send(session.browser,{type:'visitorPersona',permissionRevision:session.permissionRevision,...persona});
                for(const warning of warnings) send(session.browser,{type:'warning',message:warning});
                return;
            }
            if (message.type === 'visitorPreferences') {
                if (!session.connected || message.permissionRevision !== session.permissionRevision) return;
                try {
                    const preferences = validateVisitorPreferences({bookmarks:message.bookmarks, ...(message.home !== undefined ? {home:message.home} : {})});
                    send(session.browser, {type:'visitorPreferences', permissionRevision:session.permissionRevision, ...preferences});
                } catch { send(session.browser, {type:'warning', message:'Native bookmark changes contain an unsupported address or exceed the browser preference limits. Existing saved browser preferences were preserved.'}); }
                return;
            }
            if (message.type === 'navigationRequest' || message.type === 'navigationHistoryRequest') {
                if (!session.connected || session.navigationPending) return;
                const navigation = validateNativeNavigation(message, session.permissionRevision);
                if (message.type === 'navigationHistoryRequest') { send(session.browser, navigation); return; }
                const revision = session.permissionRevision;
                session.navigationPending = true;
                try {
                    const target = await admittedNavigationTarget(navigation.address, { domains, publicPlaces });
                    if (session.closed || !session.connected || !session.permissionsApproved || session.permissionRevision !== revision || session.native !== native) return;
                    // Revoke before asking the browser to perform fresh admission.
                    session.close(false);
                    send(session.browser, { type: 'navigation', nonce: navigation.nonce, permissionRevision: revision, domain: target });
                } catch (error) {
                    if (!session.closed && session.permissionRevision === revision) send(session.browser, { type: 'warning', message: error.message });
                } finally { session.navigationPending = false; }
                return;
            }
            if (message.type === 'poseRequest') {
                if (!session.connected) return;
                session.pendingNativePose = nativePoseRequest(message, session.permissionRevision);
                clearTimeout(session.navigationTimeout);
                session.navigationTimeout = setTimeout(() => {
                    if (!session.closed && session.pendingNativePose) {
                        send(session.browser, { type: 'state', state: 'error', message: 'Native navigation could not be applied by the browser within 15 seconds. Leave and reconnect.' });
                        session.close(false);
                    }
                }, 15000);
                send(session.browser, session.pendingNativePose); return;
            }
            if (message.type === 'tablet') {
                if (message.kind === 'microphone' && typeof message.muted === 'boolean') session.muted = message.muted;
                session.tablet?.receiveNative(message).catch(() => {
                    if (!session.closed) send(session.browser, { type: 'warning', message: 'The native tablet display could not be processed.' });
                });
                return;
            }
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
                if (message.type === 'entities' || message.type === 'entityUpdates') {
                    if (session.browser.bufferedAmount >= 4 * 1024 * 1024) {
                        // Incremental updates cannot be dropped without permanently
                        // desynchronizing the world. Close so a rejoin obtains a snapshot.
                        session.browser.close(1013, 'World updates exceeded the connection buffer. Rejoin to reload the world.');
                        session.close(false); return;
                    }
                    const hidden = message.entities.filter(entity => entity.type === 'Model' && !entity.modelURL).length;
                    if (hidden && !session.warnedAssetPermission) {
                        session.warnedAssetPermission = true;
                        send(session.browser, { type: 'warning', message: 'This domain does not expose model URLs to this visitor. Some models cannot be displayed; request asset URL viewing permission from the domain owner.' });
                    }
                }
                if (message.type === 'state' && message.state === 'connected') { message.permissionRevision = session.permissionRevision; session.connected = true; clearTimeout(session.connectionTimeout); }
                if (message.type === 'state' && message.state === 'connecting') { session.assets?.reset(); session.pendingNativePose = null; clearTimeout(session.navigationTimeout); session.permissionsApproved = false; session.connected = false; session.waitForDomain(); }
                send(session.browser, { ...message, sessionId: session.id });
                if (message.type === 'state' && message.state === 'error') session.close(false);
            }
        } catch (error) {
            // Keep the underlying cause private; expose only the protocol category.
            if (session) session.bridgeFailure = { kind: messageKind, reason: String(error.message).slice(0, 512) };
            native.close();
        }
    });
    native.on('close', () => { clearTimeout(timer); sockets.delete(native); if (session && !session.closed) {
        send(session.browser, { type: 'state', state: 'error', message: session.bridgeFailure
            ? `The native bridge rejected invalid ${session.bridgeFailure.kind} data. Leave and reconnect.`
            : 'The native domain bridge disconnected.' }); session.close(false);
    } });
    native.on('error', () => {});
});
const heartbeat = setInterval(() => {
    for (const session of sessions.values()) {
        if (session.native && Date.now() - session.lastNativeMessage > 60000) {
            send(session.browser, { type: 'state', state: 'error', message: 'The native bridge stopped responding. You can join again.' }); session.close(false);
        }
    }
    for (const socket of sockets) {
        if (socket.nativeHeartbeat) { if (!socket.nativeHeartbeat.tick()) socket.terminate(); continue; }
        if (socket.gatewayAlive === false) { socket.terminate(); continue; }
        socket.gatewayAlive = false; socket.ping();
    }
}, 30000);
let checkingPolicies = false;
const policyWatchdog = setInterval(async () => {
    if (checkingPolicies || ![...sessions.values()].some(session => session.permissionPolicy)) return;
    checkingPolicies = true;
    try {
        const policies = await readPolicyFile(process.env.OVERTE_GATEWAY_GUEST_POLICY, domains);
        for (const session of sessions.values()) {
            if (!session.permissionPolicy) continue;
            const current = policies.get(session.policyDomain || session.domain);
            if (!current || current.settingsFile !== session.permissionPolicy.settingsFile || JSON.stringify(current.permissions) !== JSON.stringify(session.permissionPolicy.permissions)) {
                session.permissionsApproved = false;
                send(session.browser, { type: 'state', state: 'error', message: 'The domain guest permission policy changed. Connection revoked; review the policy before reconnecting.' });
                session.close(false);
            }
        }
    } catch {
        for (const session of sessions.values()) {
            if (!session.permissionPolicy) continue;
            session.permissionsApproved = false;
            send(session.browser, { type: 'state', state: 'error', message: 'The domain guest permission policy is no longer valid. Connection revoked.' });
            session.close(false);
        }
    } finally { checkingPolicies = false; }
}, 10000);
let checkingPublicPlaces = false;
const publicPlaceWatchdog = setInterval(async () => {
    if (checkingPublicPlaces || shuttingDown) return;
    const active = [...sessions.values()].filter(session => session.publicPlace && !session.closed);
    if (!active.length) return;
    checkingPublicPlaces = true;
    try {
        await Promise.all(active.map(async session => {
            try {
                const current = await resolvePublicPlace(session.publicPlace.name, publicPlaces);
                if (new URL(current.nativeDomain).host !== new URL(session.nativeDomain).host ||
                    current.domainId !== session.publicPlace.domainId || current.protocolVersion !== session.publicPlace.protocolVersion) throw Error('Public place destination changed.');
            } catch {
                if (!session.closed) {
                    session.permissionsApproved = false;
                    send(session.browser, { type: 'state', state: 'error', message: 'The public place is no longer available with its approved destination, protocol and unlimited capacity. Rejoin after Directory Services recovers.' });
                    session.close(false);
                }
            }
        }));
    } finally { checkingPublicPlaces = false; }
}, 30000);
for (const websocketServer of [browserServer, nativeServer]) websocketServer.on('connection', socket => {
    socket.gatewayAlive = true; socket.on('pong', () => { socket.gatewayAlive = true; });
});
server.listen(port, host, () => console.log(`Overte browser gateway: http://${host}:${port} (${domains.length} managed domain(s), ${publicPlaces.length} public place(s))`));
function shutdown() {
    if (shutdownPromise) return shutdownPromise;
    shuttingDown = true;
    clearInterval(heartbeat);
    clearInterval(policyWatchdog);
    clearInterval(publicPlaceWatchdog);
    shutdownPromise = (async () => {
        await Promise.all([...sessions.values()].map(session => session.close()));
        for (const socket of sockets) socket.terminate();
        await new Promise(resolve => server.close(resolve));
        process.exit(0);
    })();
    return shutdownPromise;
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, shutdown);
