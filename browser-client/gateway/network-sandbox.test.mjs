// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile, readFile, rm, access, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { scopedNativeRelay, launchNativeNetwork } from './network-sandbox.mjs';
import { sandboxCommand } from './worker-sandbox.mjs';
import { terminateProcess } from './process-lifecycle.mjs';
import { safePreparationDiagnostic } from './preparation-diagnostics.mjs';
import { networkTestStderr } from './network-test-stderr.mjs';

function preparationFailure(error) {
    const diagnostic = safePreparationDiagnostic(error?.networkPreparation);
    if (diagnostic) error.message += ' [native-preparation: ' + JSON.stringify(diagnostic) + ']';
    return error;
}

async function request(socketPath, header) {
    const client = net.connect(socketPath);
    client.on('error', () => {});
    const chunks = [];
    client.on('data', data => chunks.push(data));
    client.once('connect', () => client.write(header));
    await once(client, 'close');
    return Buffer.concat(chunks).toString();
}

test('private Unix ingress exposes only the fixed native upgrade, never browser/API endpoints', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-net-relay-'));
    let relay;
    const headers = [];
    const target = net.createServer(client => client.once('data', data => {
        headers.push(data.toString()); client.end('HTTP/1.1 101 Switching Protocols\r\n\r\nactual-native-stream');
    }));
    target.listen(0, '127.0.0.1'); await once(target, 'listening');
    try {
        const socketPath = path.join(directory, 'native.socket');
        relay = await scopedNativeRelay({ socketPath, port: target.address().port, nativePath: '/native' });
        for (const header of ['GET /api/session HTTP/1.1\r\nUpgrade: websocket\r\n\r\n',
            'GET /session HTTP/1.1\r\nUpgrade: websocket\r\n\r\n',
            'GET /native?other=true HTTP/1.1\r\nUpgrade: websocket\r\n\r\n',
            'POST /native HTTP/1.1\r\nUpgrade: websocket\r\n\r\n',
            'GET /native HTTP/1.1\r\n\r\n', 'x'.repeat(17000)]) assert.equal(await request(socketPath, header), '');
        assert.equal(headers.length, 0);
        const valid = 'GET /native HTTP/1.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: YWJjZGVmZ2hpamtsbW5vcA==\r\n\r\n';
        for (const invalid of [valid.replace('Connection: Upgrade\r\n', ''), valid.replace('13\r\n', '12\r\n'),
            valid.replace('\r\n\r\n', '\r\nContent-Length: 0\r\n\r\n'), valid + 'GET /api/session HTTP/1.1\r\n\r\n',
            valid.replace('Upgrade: websocket', 'Upgrade: websocket\r\nUpgrade: websocket')]) assert.equal(await request(socketPath, invalid), '');
        assert.equal(headers.length, 0);
        const result = await request(socketPath, valid);
        assert.match(result, /actual-native-stream/); assert.equal(headers.length, 1);
    } finally {
        await relay?.close(); await new Promise(resolve => target.close(resolve));
        await rm(directory, { recursive: true, force: true });
    }
});

test('actual nested native network denies host/LAN routes and route tampering while its scoped bridge works',
    { skip: process.platform !== 'linux' }, async () => {
    const directory = await mkdtemp(path.join(tmpdir(), process.env.OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP==='1'?'overte-browser-':'overte-net-worker-'));
    const owned = [];
    const stderr = networkTestStderr(); let failed;
    const target = net.createServer(client => client.once('data', () => client.end('HTTP/1.1 101 Switching Protocols\r\n\r\nowned-native-bridge')));
    target.listen(0, '127.0.0.1'); await once(target, 'listening');
    let network;
    try {
        const port = target.address().port;
        await writeFile(path.join(directory, 'machine-id'), 'a'.repeat(32) + '\n');
        const probe = `
import socket,json,subprocess,pathlib,os
result={}
for address in ['192.168.1.1','172.20.1.1','169.254.169.254','100.64.0.1']:
    result[address]=subprocess.run(['ip','route','get',address],capture_output=True).returncode!=0
result['cannotChangeRoutes']=subprocess.run(['ip','route','delete','prohibit','192.168.0.0/16'],capture_output=True).returncode!=0
routes=subprocess.run(['ip','-j','route','show','type','prohibit'],capture_output=True)
requiredRoutes={'10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','100.64.0.0/10','192.0.0.0/24','192.0.2.0/24','198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4'}
result['allTwelveProhibitRoutesPresent']=routes.returncode==0 and requiredRoutes<={row.get('dst') for row in json.loads(routes.stdout)}
status=pathlib.Path('/proc/self/status').read_text().splitlines()
result['allFiveNativeCapabilitySetsZero']=all(sum(line.startswith(field+':') and int(line.split(':')[1].strip(),16)==0 for line in status)==1 for field in ['CapInh','CapPrm','CapEff','CapBnd','CapAmb'])
result['nativeNoNewPrivileges']=any(line.startswith('NoNewPrivs:') and line.split(':')[1].strip()=='1' for line in status)

try:
    client=socket.create_connection(('10.0.2.2',${port}),timeout=1);client.close();result['hostLoopbackDenied']=False
except OSError:result['hostLoopbackDenied']=True
client=socket.create_connection(('127.0.0.1',${port}),timeout=2)
client.sendall(b'GET /native HTTP/1.1\\r\\nUpgrade: websocket\\r\\nConnection: Upgrade\\r\\nSec-WebSocket-Version: 13\\r\\nSec-WebSocket-Key: YWJjZGVmZ2hpamtsbW5vcA==\\r\\n\\r\\n')
result['scopedBridgeWorks']=b'owned-native-bridge' in client.recv(4096);client.close()
result['noSupervisorCredentials']=not os.environ.get('OVERTE_SYNTHETIC_SECRET')
pathlib.Path(${JSON.stringify(path.join(directory, 'proof.json'))}).write_text(json.dumps(result))
raise SystemExit(0 if all(result.values()) else 1)
`;
        const worker = await sandboxCommand({ directory, executable: await realpath('/usr/bin/python3'), env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
        let slirpExecutable = process.env.OVERTE_GATEWAY_SLIRP || 'slirp4netns';
        const local = new URL('../../build/browser-native-net/root/usr/bin/slirp4netns', import.meta.url);
        try { await access(local); slirpExecutable = local.pathname; } catch { /* CI installs the official package. */ }
        network = await launchNativeNetwork({ directory, command: worker.command, args: [...worker.args, '-c', probe], env: worker.env,
            hostPort: port, nativePath: '/native', slirpExecutable, signal: new AbortController().signal,
            spawnOwned(command, args, env, label, options) {
                const child = spawn(command, args, { env: { ...env, OVERTE_SYNTHETIC_SECRET: 'must-not-inherit' }, stdio: ['pipe', 'pipe', 'pipe', ...(options ? [options.configurationFD] : [])] });
                owned.push(child); stderr.watch(child); return child;
            } });
        if (network.child.exitCode === null) await once(network.child, 'exit');
        const result = JSON.parse(await readFile(path.join(directory, 'proof.json'), 'utf8'));
        assert.ok(Object.values(result).every(value => value === true), JSON.stringify(result));
        assert.equal(network.child.exitCode, 0);
    } catch (error) {
        failed=error; throw preparationFailure(error);
    } finally {
        await network?.release(); await Promise.all(owned.map(child => terminateProcess(child, 100)));
        await new Promise(resolve => target.close(resolve)); await rm(directory, { recursive: true, force: true });
        await stderr.finish(failed);
    }
});

test('abrupt gateway death also removes the actual network owner, helper and native PID namespace',
    { skip: process.platform !== 'linux' }, async () => {
    const directory = await mkdtemp(path.join(tmpdir(), process.env.OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP==='1'?'overte-browser-':'overte-net-parent-death-'));
    let parent;
    const stderr = networkTestStderr(); let failed;
    const descendants = new Set();
    try {
        await writeFile(path.join(directory, 'machine-id'), 'b'.repeat(32) + '\n');
        let slirpExecutable = process.env.OVERTE_GATEWAY_SLIRP || 'slirp4netns';
        const local = new URL('../../build/browser-native-net/root/usr/bin/slirp4netns', import.meta.url);
        try { await access(local); slirpExecutable = local.pathname; } catch { /* CI uses its reviewed system helper. */ }
        const fixture = `
          import {spawn} from 'node:child_process';
          import {readFile,realpath} from 'node:fs/promises';
          import {launchNativeNetwork} from ${JSON.stringify(new URL('./network-sandbox.mjs', import.meta.url).href)};
          import {sandboxCommand} from ${JSON.stringify(new URL('./worker-sandbox.mjs', import.meta.url).href)};
          import {safePreparationDiagnostic} from ${JSON.stringify(new URL('./preparation-diagnostics.mjs', import.meta.url).href)};
          const worker=await sandboxCommand({directory:${JSON.stringify(directory)},executable:await realpath('/usr/bin/python3'),env:{PATH:'/usr/bin:/bin'}});
          const owned=[];
          const network=await launchNativeNetwork({directory:${JSON.stringify(directory)},command:worker.command,
            args:[...worker.args,'-c',${JSON.stringify(`import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path(${JSON.stringify(path.join(directory,'native-ready'))}).write_text('TERM-resistant native process is running'); time.sleep(600)`)}],
            env:worker.env,hostPort:40999,nativePath:'/native',slirpExecutable:${JSON.stringify(slirpExecutable)},
            signal:new AbortController().signal,
            spawnOwned(command,args,env,label,options){const child=spawn(command,args,{env,stdio:['pipe','pipe','pipe',...(options?[options.configurationFD]:[])]});owned.push(child);child.stderr.pipe(process.stderr,{end:false});return child;}}).catch(error=>{console.log(JSON.stringify({preparationFailure:safePreparationDiagnostic(error.networkPreparation)}));throw error;});
          let nativeReady=false;
          for(let attempt=0;attempt<1000;attempt++){
            try{nativeReady=(await readFile(${JSON.stringify(path.join(directory,'native-ready'))},'utf8'))==='TERM-resistant native process is running';}catch{}
            if(nativeReady)break;
            await new Promise(resolve=>setTimeout(resolve,10));
          }
          if(!nativeReady)throw Error('Actual TERM-resistant native process did not start');
          console.log(JSON.stringify({owner:network.child.pid,helper:network.helper.pid}));
          setInterval(()=>{},1000);`;
        parent = spawn(process.execPath, ['--input-type=module', '-e', fixture], { stdio: ['ignore', 'pipe', 'pipe'] });
        stderr.watch(parent);
        const value = await new Promise((resolve, reject) => {
            let output = '';
            const timer = setTimeout(() => reject(Error('Actual gateway fixture did not initialize its private network')), 15000);
            parent.once('exit', () => { clearTimeout(timer); reject(Error('Actual gateway fixture exited before network initialization')); });
            parent.stdout.on('data', chunk => {
                output += chunk.toString();
                const line = output.split('\n').find(line => line.startsWith('{'));
                if (line) {
                    clearTimeout(timer);
                    const record = JSON.parse(line);
                    if ('preparationFailure' in record) {
                        const diagnostic = safePreparationDiagnostic(record.preparationFailure);
                        reject(Error('Actual gateway fixture network preparation failed' + (diagnostic ? ': ' + JSON.stringify(diagnostic) : ' (unclassified)')));
                    } else resolve(record);
                }
            });
        });
        descendants.add(value.owner); descendants.add(value.helper);
        async function inspect(pid) {
            let children;
            try { children = (await readFile(`/proc/${pid}/task/${pid}/children`, 'utf8')).trim().split(/\s+/).filter(Boolean).map(Number); }
            catch { return; }
            for (const child of children) { descendants.add(child); await inspect(child); }
        }
        await inspect(value.owner);
        assert.ok(descendants.size >= 4, 'The actual native-style namespace has supervisor and process descendants');
        const exited = once(parent, 'exit'); parent.kill('SIGKILL'); await exited;
        let survivors = [...descendants];
        for (let attempt = 0; attempt < 500 && survivors.length; attempt++) {
            survivors = survivors.filter(pid => { try { process.kill(pid, 0); return true; } catch { return false; } });
            if (survivors.length) await new Promise(resolve => setTimeout(resolve, 10));
        }
        const remaining = await Promise.all(survivors.map(async pid => {
            const stat = await readFile(`/proc/${pid}/stat`, 'utf8').catch(() => 'already reaped');
            return { role: pid === value.owner ? 'owner' : pid === value.helper ? 'helper' : 'native descendant', stat };
        }));
        assert.deepEqual(survivors, [], `Parent death cannot orphan a gateway native worker or network helper: ${JSON.stringify(remaining)}`);
    } catch(error) { failed=error; throw error; } finally {
        if (parent) await terminateProcess(parent, 100);
        for (const pid of descendants) { try { process.kill(pid, 'SIGKILL'); } catch { /* Already reaped as asserted. */ } }
        await rm(directory, { recursive: true, force: true });
        await stderr.finish(failed);
    }
});

test('real managed UDP route forwards only fixed domain/mixer ports from the isolated native network',
    { skip: process.platform !== 'linux' }, async () => {
    const { createSocket } = await import('node:dgram');
    const directory = await mkdtemp(path.join(tmpdir(), process.env.OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP==='1'?'overte-browser-':'overte-net-managed-'));
    const owned = [];
    const stderr = networkTestStderr(); let failed;
    const domain = createSocket('udp4');
    const forbidden = createSocket('udp4');
    let forbiddenPackets = 0, network;
    domain.on('message', (message, peer) => domain.send(Buffer.concat([Buffer.from('real-domain:'), message]), peer.port, peer.address));
    forbidden.on('message', () => forbiddenPackets++);
    domain.bind(0, '127.0.0.2'); forbidden.bind(0, '127.0.0.2');
    await Promise.all([once(domain, 'listening'), once(forbidden, 'listening')]);
    try {
        await writeFile(path.join(directory, 'machine-id'), 'c'.repeat(32) + '\n');
        const probe = `
import socket,json,pathlib
peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.settimeout(2)
peer.sendto(b'authenticated-native-test',('127.0.0.2',${domain.address().port}))
data,source=peer.recvfrom(4096)
result={'realBytes':data==b'real-domain:authenticated-native-test','sourcePort':source[1]==${domain.address().port},'sourceAddress':source[0]=='127.0.0.2'}
peer.sendto(b'must-not-arrive',('127.0.0.2',${forbidden.address().port}))
peer.settimeout(.2)
try:peer.recvfrom(4096);result['forbiddenPortDenied']=False
except socket.timeout:result['forbiddenPortDenied']=True
pathlib.Path(${JSON.stringify(path.join(directory, 'proof.json'))}).write_text(json.dumps(result))
raise SystemExit(0 if all(result.values()) else 1)
`;
        const worker = await sandboxCommand({ directory, executable: await realpath('/usr/bin/python3'), env: { PATH: '/usr/bin:/bin' } });
        let slirpExecutable = process.env.OVERTE_GATEWAY_SLIRP || 'slirp4netns';
        const local = new URL('../../build/browser-native-net/root/usr/bin/slirp4netns', import.meta.url);
        try { await access(local); slirpExecutable = local.pathname; } catch { /* Installed CI package. */ }
        network = await launchNativeNetwork({ directory, command: worker.command, args: [...worker.args, '-c', probe], env: worker.env,
            hostPort: 40998, nativePath: '/native', slirpExecutable, managedUDP: { address: '127.0.0.2', ports: [domain.address().port] },
            signal: new AbortController().signal, spawnOwned(command, args, env, label, options) {
                const child = spawn(command, args, { env, stdio: ['pipe', 'pipe', 'pipe', ...(options ? [options.configurationFD] : [])] });
                owned.push(child); stderr.watch(child); return child;
            } });
        if (network.child.exitCode === null) await once(network.child, 'exit');
        const proof = JSON.parse(await readFile(path.join(directory, 'proof.json'), 'utf8'));
        assert.ok(Object.values(proof).every(value => value === true), JSON.stringify(proof));
        assert.equal(network.child.exitCode, 0);
        assert.equal(forbiddenPackets, 0);
    } catch (error) {
        failed=error; throw preparationFailure(error);
    } finally {
        await network?.release(); await Promise.all(owned.map(child => terminateProcess(child, 100)));
        domain.close(); forbidden.close(); await rm(directory, { recursive: true, force: true });
        await stderr.finish(failed);
    }
});
