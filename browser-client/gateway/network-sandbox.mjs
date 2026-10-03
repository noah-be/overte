// SPDX-License-Identifier: Apache-2.0
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chmod, writeFile, rm } from 'node:fs/promises';
import { once } from 'node:events';
import { terminateProcess } from './process-lifecycle.mjs';
import {trustedNetworkEntry} from './trusted-network-entry.mjs';
import {networkWorkerEnvironment} from './network-worker-environment.mjs';
import { preparationDiagnostics, helperPreparationDiagnostics } from './preparation-diagnostics.mjs';

const owner = fileURLToPath(new URL('./network-owner.py', import.meta.url));
const udpOwner = fileURLToPath(new URL('./network_udp.py', import.meta.url));
const supervisorEnvironment = { PATH: '/usr/bin:/bin:/usr/sbin:/sbin', LANG: 'C.UTF-8' };
const stopChild = child => child ? terminateProcess(child) : Promise.resolve();

function lineFrom(child, expected, signal, timeout = 12000) {
    return new Promise((resolve, reject) => {
        let data = '';
        const diagnostics = preparationDiagnostics(expected);
        const stderr = chunk => diagnostics.observe(chunk);
        const timer = setTimeout(() => finish(Error('Native network supervisor timed out')), timeout);
        const abort = () => finish(signal?.reason || Error('Native network preparation cancelled'));
        const exited = () => {
            const error = Error('Native network supervisor exited during preparation');
            error.networkPreparation = diagnostics.snapshot(child.exitCode, child.signalCode);
            finish(error);
        };
        const failed = () => finish(Error('Native network supervisor could not start'));
        const output = chunk => {
            data = (data + chunk.toString()).slice(-32768);
            if (data.split('\n').includes(expected)) finish();
        };
        function finish(error) {
            clearTimeout(timer); child.stdout.off('data', output); child.off('exit', exited); child.off('error', failed);
            child.stderr?.off('data', stderr);
            signal?.removeEventListener('abort', abort);
            if (error) reject(error); else resolve();
        }
        child.stdout.on('data', output); child.once('exit', exited); child.once('error', failed);
        child.stderr?.on('data', stderr);
        signal?.addEventListener('abort', abort, { once: true });
        if (signal?.aborted) abort();
        else if (child.exitCode !== null || child.signalCode !== null) exited();
    });
}

/** The Unix ingress exposes exactly one session's native WebSocket upgrade. */
export async function scopedNativeRelay({ socketPath, port, nativePath }) {
    if (!/^\/native(?:\/[a-zA-Z0-9_-]{1,128})?$/.test(nativePath) || !Number.isInteger(port) || port < 1 || port > 65535) throw Error('Invalid native relay scope');
    const clients = new Set();
    const server = net.createServer(client => {
        clients.add(client); client.once('close', () => clients.delete(client));
        client.on('error', () => client.destroy()); client.setTimeout(5000, () => client.destroy());
        let header = Buffer.alloc(0);
        const initial = data => {
            header = Buffer.concat([header, data]);
            if (header.length > 16384) { client.destroy(); return; }
            const end = header.indexOf('\r\n\r\n');
            if (end < 0) return;
            const lines = header.subarray(0, end).toString('latin1').split('\r\n');
            const fields = new Map();
            for (const line of lines.slice(1)) {
                const match = /^([a-z0-9-]+):[\t ]*([\x20-\x7e]*)$/i.exec(line);
                if (!match || fields.has(match[1].toLowerCase())) { client.destroy(); return; }
                fields.set(match[1].toLowerCase(), match[2].trim());
            }
            if (lines[0] !== `GET ${nativePath} HTTP/1.1` || header.length !== end + 4
                || fields.get('upgrade')?.toLowerCase() !== 'websocket'
                || !fields.get('connection')?.toLowerCase().split(',').map(item => item.trim()).includes('upgrade')
                || fields.get('sec-websocket-version') !== '13'
                || !/^[a-zA-Z0-9+/]{22}==$/.test(fields.get('sec-websocket-key') || '')
                || fields.has('content-length') || fields.has('transfer-encoding')) { client.destroy(); return; }
            client.off('data', initial); client.pause(); client.setTimeout(0);
            const target = net.connect({ host: '127.0.0.1', port });
            clients.add(target); target.once('close', () => { clients.delete(target); client.destroy(); });
            target.on('error', () => client.destroy()); client.once('close', () => target.destroy());
            target.once('connect', () => { target.write(header); client.pipe(target); target.pipe(client); client.resume(); });
        };
        client.on('data', initial);
    });
    server.maxConnections = 8;
    server.listen(socketPath); await once(server, 'listening'); await chmod(socketPath, 0o600);
    return { async close() {
        const closed = new Promise(resolve => server.close(resolve));
        for (const client of clients) client.destroy();
        await closed; await rm(socketPath, { force: true });
    } };
}

/** Public native UDP/HTTPS plus a scoped bridge; host loopback and private routes denied. */
export async function launchNativeNetwork({ directory, command, args, env, hostPort, nativePath, spawnOwned, signal,
    slirpExecutable = 'slirp4netns', managedUDP }) {
    if (signal?.aborted) throw Error('Native network preparation cancelled');
    if (command !== 'bwrap' && path.basename(command) !== 'bwrap') throw Error('Native network requires the reviewed inner bubblewrap boundary');
    if (!args.includes('--unshare-user') || args.includes('--share-net')) throw Error('Native inner worker must create its own user namespace');
    const trustedSetup = process.env.OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP === '1';
    const bridgeSocket = path.join(directory, 'native-network.socket');
    const relay = await scopedNativeRelay({ socketPath: bridgeSocket, port: hostPort, nativePath });
    if (managedUDP && (net.isIP(managedUDP.address) !== 4 || !managedUDP.address.startsWith('127.')
        || !Array.isArray(managedUDP.ports) || managedUDP.ports.length < 1 || managedUDP.ports.length > 32
        || managedUDP.ports.some(port => !Number.isInteger(port) || port < 1 || port > 65535))) {
        await relay.close(); throw Error('Managed native network requires explicit loopback UDP ports');
    }
    let child, helper, udpHelper;
    let preparationPhase = 'OVERTE_UDP_RELAY_READY';
    const helperDiagnostics = helperPreparationDiagnostics();
    const spawnHelper = (role, ...parameters) => {
        try { return helperDiagnostics.watch(role, spawnOwned(...parameters)); }
        catch (error) { helperDiagnostics.spawnFailure(role, error); throw error; }
    };
    try {
        const configPath = path.join(directory, 'native-network.json');
        const resolver = path.join(directory, 'network-resolv.conf');
        await writeFile(resolver, 'nameserver 10.0.2.3\noptions timeout:2 attempts:2\n', { mode: 0o600 });
        const privateArgs = [...args];
        const resolverIndex = privateArgs.indexOf('/etc/resolv.conf');
        if (resolverIndex >= 0) privateArgs[resolverIndex] = resolver;
        else privateArgs.splice(privateArgs.indexOf('--'), 0, '--ro-bind', resolver, '/etc/resolv.conf');
        await writeFile(configPath, JSON.stringify({ command, args: privateArgs,
            environment: trustedSetup ? networkWorkerEnvironment(privateArgs) : env, bridgePort: hostPort, bridgeSocket,
            ...(managedUDP ? { managedUDP, managedUDPSocket: path.join(directory, 'managed-udp.socket') } : {}),
            supervisorParentPID: process.pid }), { mode: 0o600 });
        if (signal?.aborted) throw Error('Native network preparation cancelled');
        if (managedUDP) {
            udpHelper = spawnHelper('managed-udp', '/usr/bin/python3', [udpOwner, configPath], supervisorEnvironment, 'Managed domain UDP relay');
            await lineFrom(udpHelper, 'OVERTE_UDP_RELAY_READY', signal);
        }
        preparationPhase = 'OVERTE_NET_OWNER_READY';
        if (trustedSetup) {
            const trusted = await trustedNetworkEntry(configPath);
            try {
                if (signal?.aborted) throw Error('Native network preparation cancelled');
                child = spawnOwned(trusted.command, trusted.args, supervisorEnvironment, 'Private native network', trusted.options);
            } finally { await trusted.close(); }
        } else {
            child = spawnOwned('unshare', ['--user', '--map-root-user', '--net', '/usr/bin/python3', owner, configPath], supervisorEnvironment, 'Private native network');
        }
        await lineFrom(child, 'OVERTE_NET_OWNER_READY', signal);
        helperDiagnostics.ownerReady();
        preparationPhase = 'OVERTE_NET_NATIVE_STARTED';
        const started = lineFrom(child, 'OVERTE_NET_NATIVE_STARTED', signal);
        // Preserve the rejection for the awaited preparation while ensuring a
        // synchronous helper-spawn error cannot leave an unhandled waiter.
        started.catch(() => {});
        helper = spawnHelper('slirp', slirpExecutable, ['--configure', '--disable-host-loopback', '--mtu=65520', '--exit-fd=0', String(child.pid), 'tap0'], supervisorEnvironment, 'Native network helper');
        helper.once('error', () => child.kill('SIGTERM'));
        const helperExited = (code, signal) => {
            // A successful helper exits when the owner closes its namespace /
            // relay. Different process pipes can report that completion before
            // Node observes the owner's own exit. Do not terminate a successfully
            // exiting Python interpreter after its signal handlers are removed.
            if ((code !== 0 || signal) && child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
        };
        helper.once('exit', helperExited);
        udpHelper?.once('exit', helperExited);
        await started;
        helperDiagnostics.stop();
        return { child, helper, udpHelper, async release() { await Promise.all([stopChild(child), stopChild(helper), stopChild(udpHelper)]); await relay.close(); } };
    } catch (error) {
        helperDiagnostics.attach(error, preparationPhase);
        helperDiagnostics.stop();
        await Promise.all([stopChild(child), stopChild(helper), stopChild(udpHelper)]); await relay.close(); throw error;
    }
}
