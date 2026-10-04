// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, mkdir, readFile, writeFile, rm, access, symlink } from 'node:fs/promises';
import { tmpdir, homedir } from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { workerEnvironment, prepareWorker, sandboxCommand } from './worker-sandbox.mjs';
import { terminateProcess } from './process-lifecycle.mjs';
import { workerSurvivorState } from './worker-process-diagnostics.mjs';
import { x11ProbeDiagnostic } from './x11-probe-diagnostics.mjs';

const run = promisify(execFile);

// CPU-testable failure projection. The original failure still propagates.
function workerX11FailureDiagnostic(error, workerOrdinal) {
    const value = error?.x11ReadinessDiagnostic;
    if (![1, 2].includes(workerOrdinal) || !value || typeof value !== 'object' || Array.isArray(value)
        || Object.keys(value).length !== 4 || typeof value.connectReached !== 'boolean'
        || typeof value.writeInvoked !== 'boolean' || (value.writeInvoked && !value.connectReached)
        || !Number.isSafeInteger(value.responseBytes) || value.responseBytes < 0 || value.responseBytes > 65536
        || (value.validatedExpectedBytes !== null && (!Number.isSafeInteger(value.validatedExpectedBytes)
            || value.validatedExpectedBytes < 40 || value.validatedExpectedBytes > 65536))
        || (value.validatedExpectedBytes !== null && value.responseBytes < 8)) return null;
    return {workerOrdinal, connectReached:value.connectReached, writeInvoked:value.writeInvoked,
        responseBytes:value.responseBytes, validatedExpectedBytes:value.validatedExpectedBytes};
}
test('native worker environment excludes operator credentials, accounts and shared desktop', () => {
    const env = workerEnvironment('/session', { GITHUB_TOKEN: 'synthetic-secret', SSH_AUTH_SOCK: '/operator/ssh.sock',
        HOME: '/operator', DISPLAY: ':0', XAUTHORITY: '/operator/Xauthority',
        PULSE_SERVER: 'unix:/session/pulse.socket', LD_LIBRARY_PATH: '/approved/native/lib' });
    assert.equal(env.HOME, '/session'); assert.equal(env.XDG_CONFIG_HOME, '/session/config');
    assert.equal(env.LD_LIBRARY_PATH, '/approved/native/lib');
    for (const key of ['GITHUB_TOKEN', 'SSH_AUTH_SOCK', 'DISPLAY', 'XAUTHORITY']) assert.equal(env[key], undefined);
});

test('runtime aliases retain their guest paths but cannot expose broad or private operator roots', async () => {
    const directory = await mkdtemp(path.join(tmpdir(),'overte-runtime-alias-test-'));
    try {
        const installed = path.join(directory,'installed'), alias = path.join(directory,'native-alias');
        await mkdir(installed);await symlink(installed,alias);
        const launch = await sandboxCommand({directory,executable:process.execPath,env:{},roots:[alias]});
        const binding = launch.args.indexOf(alias);
        assert.equal(launch.args[binding-1],'--ro-bind');assert.equal(launch.args[binding+1],alias);
        for (const [index,target] of [homedir(),'/','/tmp','/etc'].entries()) {
            const unsafeAlias = path.join(directory,`unsafe-alias-${index}`);
            await symlink(target,unsafeAlias);
            await assert.rejects(sandboxCommand({directory,executable:process.execPath,env:{},roots:[unsafeAlias]}),
                /installed packages, not operator profiles/);
        }
        const privateRoot = path.join(directory,'operator','.ssh');await mkdir(privateRoot,{recursive:true});
        const privateAlias = path.join(directory,'private-alias');await symlink(privateRoot,privateAlias);
        await assert.rejects(sandboxCommand({directory,executable:process.execPath,env:{},roots:[privateAlias]}),
            /installed packages, not operator profiles/);
    } finally {await rm(directory,{recursive:true,force:true});}
});

test('Graphics overrides bind only six exact installed targets from the owned worker profile',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-graphics-bind-test-'));
    try{
        const profile=path.join(directory,'profile'),nativeRoot=path.join(directory,'installed');await mkdir(profile);
        const names=['settings.js','Settings.qml','qml/pages/GraphicsSettings.qml','qml/SettingSlider.qml','qml/SettingBoolean.qml','qml/SettingComboBox.qml'];
        const overrides=[];
        for(const [index,name] of names.entries()){
            const source=path.join(profile,`browser-graphics-override-${index+1}${name.endsWith('.qml')?'.qml':'.js'}`),target=path.join(nativeRoot,'scripts/system/settings',name);
            await mkdir(path.dirname(target),{recursive:true});await writeFile(source,'owned prepared adapter');await writeFile(target,'installed original');overrides.push({source,target});
        }
        const config={directory:profile,executable:process.execPath,env:{},roots:[nativeRoot]};
        const launch=await sandboxCommand({...config,readOnlyOverrides:overrides});
        for(const {source,target} of overrides){const index=launch.args.indexOf(source);assert.equal(launch.args[index-1],'--ro-bind');assert.equal(launch.args[index+1],target);assert.equal(await readFile(target,'utf8'),'installed original');}
        await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{...overrides[0],target:overrides[1].target}]}),/Only reviewed session/);
        const sibling=path.join(directory,'sibling');await mkdir(sibling);const otherSource=path.join(sibling,path.basename(overrides[0].source));await writeFile(otherSource,'another visitor');
        await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{...overrides[0],source:otherSource}]}),/Only reviewed session/);
        const arbitrary=path.join(profile,'unreviewed.qml');await writeFile(arbitrary,'arbitrary');
        await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{...overrides[2],source:arbitrary}]}),/Only reviewed session/);
        await rm(overrides[0].source);await symlink(overrides[1].source,overrides[0].source);
        await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[overrides[0]]}),/regular trusted script/);
    }finally{await rm(directory,{recursive:true,force:true});}
});

test('actual isolated worker cannot read host files, sibling profiles, host process environment or shared X credentials',
    { skip: process.platform !== 'linux' }, async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'overte-worker-test-'));
    const owned = [], workers = [];
    try {
        const first = path.join(directory, 'first'), second = path.join(directory, 'second');
        await Promise.all([mkdir(first), mkdir(second)]);
        const nativeRoot = path.join(directory, 'native-package'), snapshotTarget = path.join(nativeRoot, 'scripts/system/snapshot.js');
        await mkdir(path.dirname(snapshotTarget), { recursive: true });
        await writeFile(snapshotTarget, 'original installed snapshot script');
        const placesTarget = path.join(nativeRoot, 'scripts/system/places/places.js');
        await mkdir(path.dirname(placesTarget), {recursive:true});
        await writeFile(placesTarget, 'original installed Places script');
        const placesSource = path.join(first, 'browser-places.js');
        await writeFile(placesSource, 'trusted fresh-admission Places adapter');
        const snapshotSource = path.join(first, 'browser-snapshot.js');
        await writeFile(snapshotSource, 'trusted browser scene snapshot adapter');
        const createSource=path.join(first,'browser-create-properties.html'),createTarget=path.join(nativeRoot,'scripts/system/create/entityProperties/html/entityProperties.html');
        await mkdir(path.dirname(createTarget),{recursive:true});await writeFile(createTarget,'installed original Create Properties');
        await writeFile(createSource,'trusted responsive Create Properties',{mode:0o600});
        const graphicsOverrides=[];
        for(const [index,name] of ['settings.js','Settings.qml','qml/pages/GraphicsSettings.qml','qml/SettingSlider.qml','qml/SettingBoolean.qml','qml/SettingComboBox.qml'].entries()){
            const source=path.join(first,`browser-graphics-override-${index+1}${name.endsWith('.qml')?'.qml':'.js'}`),target=path.join(nativeRoot,'scripts/system/settings',name);
            await mkdir(path.dirname(target),{recursive:true});await writeFile(source,`trusted Graphics adapter ${index}`);await writeFile(target,`original installed Graphics ${index}`);graphicsOverrides.push({source,target});
        }
        await writeFile(path.join(second, 'private-other-session'), 'synthetic-session-secret');
        await writeFile(path.join(directory, 'private-operator-file'), 'synthetic-operator-secret');
        let xvfb = process.env.OVERTE_GATEWAY_XVFB || 'Xvfb';
        const localXvfb = new URL('../../build/browser-lab/host-tools/usr/bin/Xvfb', import.meta.url);
        try { await access(localXvfb); xvfb = localXvfb.pathname; } catch { /* CI installs Xvfb. */ }
        const previous = process.env.OVERTE_GATEWAY_XVFB; process.env.OVERTE_GATEWAY_XVFB = xvfb;
        try {
            for (const profile of [first, second]) {
                try { workers.push(await prepareWorker({ directory: profile,
                executable: process.execPath, nativeRoot,
                readOnlyOverrides: profile === first ? [{ source: snapshotSource, target: snapshotTarget }, {source:placesSource,target:placesTarget},{source:createSource,target:createTarget},...graphicsOverrides] : [],
                sourceEnvironment: { GITHUB_TOKEN: 'synthetic-secret' }, signal: new AbortController().signal,
                spawnOwned(command, args, env) { const child = spawn(command, args, { env, stdio: 'ignore' }); owned.push(child); return child; } })); }
                catch (error) {
                    const diagnostic = workerX11FailureDiagnostic(error, workers.length + 1);
                    if (diagnostic) console.error('BROWSER_X11_READINESS ' + JSON.stringify(diagnostic));
                    throw error;
                }
            }
        } finally { if (previous === undefined) delete process.env.OVERTE_GATEWAY_XVFB; else process.env.OVERTE_GATEWAY_XVFB = previous; }
        const script = `
            const fs=require('fs'),net=require('net');
            const forbidden=JSON.parse(process.argv[1]);
            const readable=forbidden.filter(p=>{try{fs.readFileSync(p);return true}catch{return false}});
            const auth=fs.readFileSync(process.env.XAUTHORITY);
            const cookie=auth.subarray(auth.length-16);
            const x11ProbeDiagnostic=${x11ProbeDiagnostic.toString()};
            function probe(number,useCookie,abstract){return new Promise(resolve=>{
                const client=net.createConnection((abstract?String.fromCharCode(0):'')+'/tmp/.X11-unix/X'+number);
                let connected=false,requestWritten=false,settled=false;
                function finish(accepted,diagnostic){if(settled)return;settled=true;client.destroy();resolve({accepted,diagnostic:{...diagnostic,connected,requestWritten}});}
                client.on('error',error=>finish(false,x11ProbeDiagnostic('socket-error',error)));client.on('data',data=>finish(data[0]===1,x11ProbeDiagnostic('setup',data)));
                client.on('connect',()=>{connected=true;const head=Buffer.alloc(12);head[0]=108;head.writeUInt16LE(11,2);
                    if(useCookie){head.writeUInt16LE(18,6);head.writeUInt16LE(16,8);const name=Buffer.alloc(20);name.write('MIT-MAGIC-COOKIE-1');client.write(Buffer.concat([head,name,cookie]),error=>{requestWritten=!error;});}
                    else client.write(head,error=>{requestWritten=!error;})});
                client.setTimeout(3000,()=>finish(false,x11ProbeDiagnostic('timeout')));
            })}
            Promise.all([probe(process.env.DISPLAY.slice(1),true),probe(process.argv[2],false),probe(process.argv[2],false,true)]).then(([own,other,otherAbstract])=>{
                const ownX=own.accepted,otherX=other.accepted,otherAbstractX=otherAbstract.accepted;
                fs.writeFileSync(process.env.HOME+'/own-file','allowed');
                console.log(JSON.stringify({readable,ownX,otherX,otherAbstractX,x11:{own:own.diagnostic,other:other.diagnostic,otherAbstract:otherAbstract.diagnostic},secret:process.env.GITHUB_TOKEN,
                    machine:fs.readFileSync('/etc/machine-id','utf8').trim(),uid:process.getuid(),
                    nssTrust:JSON.parse(process.argv[3]).map(p=>fs.readFileSync(p).length),
                    graphics:JSON.parse(process.argv[6]).map(filename=>({bytes:fs.readFileSync(filename,'utf8'),readOnly:(()=>{try{fs.writeFileSync(filename,'changed');return false}catch{return true}})()})),
                    places:fs.readFileSync(process.argv[5],'utf8'),placesReadOnly:(()=>{try{fs.writeFileSync(process.argv[5],'changed');return false}catch{return true}})(),
                    create:fs.readFileSync(process.argv[7],'utf8'),createReadOnly:(()=>{try{fs.writeFileSync(process.argv[7],'changed');return false}catch{return true}})(),
                    snapshot:fs.readFileSync(process.argv[4],'utf8'),snapshotReadOnly:(()=>{try{fs.writeFileSync(process.argv[4],'changed');return false}catch{return true}})()}));
            });`;
        const forbidden = [path.join(directory, 'private-operator-file'), path.join(second, 'private-other-session'),
            path.join(second, 'Xauthority'), `/proc/${process.pid}/environ`];
        const trustLibraries = [];
        for (const filename of ['/usr/lib64/libnssckbi.so', '/usr/lib/x86_64-linux-gnu/libnssckbi.so']) {
            try { await access(filename); trustLibraries.push(filename); } catch { /* Distribution-specific NSS library. */ }
        }
        const output = await run(workers[0].command, [...workers[0].args, '-e', script, JSON.stringify(forbidden), String(workers[1].display), JSON.stringify(trustLibraries), snapshotTarget, placesTarget,JSON.stringify(graphicsOverrides.map(value=>value.target)),createTarget],
            { env: { ...workers[0].env, GITHUB_TOKEN: 'synthetic-secret' }, timeout: 10000 });
        const result = JSON.parse(output.stdout);
        assert.deepEqual(result.readable, []); assert.equal(result.secret, undefined);
        assert.equal(result.ownX, true, 'The worker can authenticate only to its own real Xvfb: '+JSON.stringify(result.x11.own));
        assert.equal(result.otherX, false, 'Another session display and Xauthority remain inaccessible');
        assert.equal(result.otherAbstractX, false, 'Shared-network abstract X sockets also require the private cookie');
        assert.match(result.machine, /^[0-9a-f]{32}$/);
        assert.notEqual(result.uid, 0, 'Qt WebEngine runs without disabling its Chromium root/sandbox checks');
        assert.deepEqual(result.nssTrust, await Promise.all(trustLibraries.map(async filename => (await readFile(filename)).length)),
            'System NSS certificate trust libraries remain readable through their installed alternatives links');
        assert.deepEqual(result.graphics,graphicsOverrides.map((_,index)=>({bytes:`trusted Graphics adapter ${index}`,readOnly:true})));
        for(const [index,value] of graphicsOverrides.entries())assert.equal(await readFile(value.target,'utf8'),`original installed Graphics ${index}`,'The actual worker never modifies the installed Qt Settings package');
        assert.equal(result.create,'trusted responsive Create Properties');assert.equal(result.createReadOnly,true);
        assert.equal(await readFile(createTarget,'utf8'),'installed original Create Properties');
        assert.equal(result.places, 'trusted fresh-admission Places adapter'); assert.equal(result.placesReadOnly, true);
        assert.equal(await readFile(placesTarget,'utf8'), 'original installed Places script');
        assert.equal(result.snapshot, 'trusted browser scene snapshot adapter'); assert.equal(result.snapshotReadOnly, true);
        assert.equal(await readFile(snapshotTarget, 'utf8'), 'original installed snapshot script', 'The host installed script is preserved');
        await assert.rejects(sandboxCommand({ directory:first, executable:process.execPath, env:{}, roots:[nativeRoot],
            readOnlyOverrides:[{source:snapshotSource,target:'/etc/passwd'}] }), /Only reviewed session Snapshot, Places, browser Graphics and Create Properties adapters/);
        assert.equal(await readFile(path.join(first, 'own-file'), 'utf8'), 'allowed');
        const launcher = spawn(workers[0].command, [...workers[0].args, '-e', `
            const cp=require('child_process');
            const child=cp.spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});console.log('ready');setInterval(()=>{},1000)"]);
            child.stdout.on('data',()=>console.log('ready'));setInterval(()=>{},1000);`],
            { env: workers[0].env, stdio: ['ignore', 'pipe', 'ignore'] });
        owned.push(launcher);
        await once(launcher.stdout, 'data');
        const descendants = [];
        async function inspectChildren(pid) {
            const children = (await readFile(`/proc/${pid}/task/${pid}/children`, 'utf8')).trim().split(/\s+/).filter(Boolean).map(Number);
            for (const child of children) { descendants.push(child); await inspectChildren(child); }
        }
        await inspectChildren(launcher.pid);
        assert.ok(descendants.length >= 2, 'Actual PID namespace contains native-style child and its spawned descendant');
        await terminateProcess(launcher, 100);
        let survivors = descendants;
        for (let attempts = 0; attempts < 100 && survivors.length; attempts++) {
            survivors = survivors.filter(pid => { try { process.kill(pid, 0); return true; } catch { return false; } });
            if (survivors.length) await new Promise(resolve => setTimeout(resolve, 10));
        }
        const survivorStates = await Promise.all(survivors.map(workerSurvivorState));
        assert.deepEqual(survivors, [], 'Ending the owned sandbox also removes TERM-resistant namespace descendants: ' + JSON.stringify(survivorStates));
    } finally {
        await Promise.all(owned.map(child => terminateProcess(child, 100)));
        for (const child of owned) assert.throws(() => process.kill(child.pid, 0), { code: 'ESRCH' });
        for (const worker of workers) worker.release();
        await rm(directory, { recursive: true, force: true });
    }
});
