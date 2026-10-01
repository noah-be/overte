// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import vm from 'node:vm';
import path from 'node:path';
import net from 'node:net';
import { preparationDiagnostics, safePreparationDiagnostic, helperPreparationDiagnostics } from './preparation-diagnostics.mjs';
const source = await readFile(new URL('./network-sandbox.mjs',import.meta.url),'utf8');
const actual = source.slice(source.indexOf('function lineFrom('),source.indexOf('/** The Unix ingress'));
const lineFrom = vm.runInNewContext(actual+';lineFrom',{preparationDiagnostics,Promise,Error,setTimeout,clearTimeout});
test('bounded stderr yields only fixed preparation enums and never raw secrets',()=>{
 const d=preparationDiagnostics('OVERTE_NET_OWNER_READY');
 d.observe(Buffer.from('secret-private-token '.repeat(10000)));
 d.observe(Buffer.from("Private native network failed: Command '['ip', 'route', 'add', 'prohibit', '10.0.0.0/8']' returned non-zero exit status 2."));
 const out=d.snapshot(1,'SIGKILL');assert.equal(out.category,'deny-route-command-failed');assert.equal(out.truncated,true);
 assert.equal(JSON.stringify(out).includes('secret'),false);assert.equal(JSON.stringify(out).includes('10.0.'),false);assert.equal(out.exitCode,1);assert.equal(out.signal,'SIGKILL');
 assert.throws(()=>preparationDiagnostics('secret-phase'));
});
test('split stderr classification preserves refusal category without caller-controlled labels',()=>{
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');
 d.observe(Buffer.from('bwrap: Operation not '));d.observe(Buffer.from('permitted /private/secret'));
 assert.equal(d.snapshot(-1,'secret-signal').category,'inner-sandbox-refused');assert.equal(d.snapshot(-1,'secret-signal').signal,'other-signal');
});
test('actual production readiness waiter attaches safe stderr diagnosis on a real failed child',async()=>{
 const child=spawn(process.execPath,['-e',"process.stderr.write('unshare: unshare failed: Operation not permitted private-token');process.exit(3)"],{stdio:['ignore','pipe','pipe']});
 await assert.rejects(lineFrom(child,'OVERTE_NET_OWNER_READY',undefined,2000),e=>{
  assert.equal(e.message,'Native network supervisor exited during preparation');assert.equal(e.networkPreparation.category,'namespace-refused');
  assert.equal(e.networkPreparation.exitCode,3);assert.equal(JSON.stringify(e).includes('private-token'),false);return true;
 });assert.equal(child.stderr.listenerCount('data'),0);
});
test('actual production successful waiter removes diagnostic listener and remains unchanged',async()=>{
 const child=spawn(process.execPath,['-e',"console.log('OVERTE_NET_OWNER_READY')"],{stdio:['ignore','pipe','pipe']});
 await lineFrom(child,'OVERTE_NET_OWNER_READY',undefined,2000);assert.equal(child.stderr.listenerCount('data'),0);
});

test('safe fixture forwarding strips fields and refuses unknown failure labels',()=>{
 const d=preparationDiagnostics('OVERTE_NET_OWNER_READY').snapshot(1,null);
 assert.deepEqual(safePreparationDiagnostic({...d,credentials:'secret',path:'/private'}),d);
 assert.equal(safePreparationDiagnostic({...d,category:'private-token'}),null);
 assert.equal(safePreparationDiagnostic({...d,observedBytes:Infinity}),null);
 assert.equal(safePreparationDiagnostic({...d,phase:'unknown-secret'}),null);
});

test('real missing helper records only errno and stops observations before cleanup', async () => {
 const d=helperPreparationDiagnostics();
 const child=spawn('/not-present/private-helper-secret',[],{stdio:['ignore','pipe','pipe']});
 const errorEvent=new Promise(resolve=>child.once('error',resolve));
 d.watch('slirp',child);await errorEvent;
 const error=Error('original preparation failure');d.attach(error,'OVERTE_NET_OWNER_READY');d.stop();
 assert.equal(error.message,'original preparation failure');
 assert.deepEqual(error.networkPreparation.helperEvents,[{role:'slirp',kind:'spawn-error',beforeOwnerReady:true,errno:'ENOENT'}]);
 assert.equal(error.networkPreparation.category,'helper-spawn-failed');
 assert.equal(JSON.stringify(error.networkPreparation).includes('private-helper-secret'),false);
 assert.ok(Object.isFrozen(error.networkPreparation.helperEvents));
 assert.deepEqual(safePreparationDiagnostic(error.networkPreparation),error.networkPreparation);
 assert.equal(child.listenerCount('exit'),0);
});

test('real helper exit is bounded and cancellation cleanup cannot alter the captured diagnosis', async () => {
 const d=helperPreparationDiagnostics();
 const child=spawn(process.execPath,['-e','process.exit(7)'],{stdio:['ignore','pipe','pipe']});
 d.watch('managed-udp',child);await new Promise(resolve=>child.once('exit',resolve));
 d.ownerReady();
 const alive=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:['ignore','pipe','pipe']});
 d.watch('slirp',alive);
 const error=Error('fixed failure');d.attach(error,'OVERTE_NET_NATIVE_STARTED');d.stop();
 const before=JSON.stringify(error.networkPreparation);
 const exited=new Promise(resolve=>alive.once('exit',resolve));alive.kill('SIGTERM');await exited;
 assert.equal(JSON.stringify(error.networkPreparation),before);
 assert.equal(error.networkPreparation.category,'helper-exited-during-preparation');
 assert.deepEqual(error.networkPreparation.helperEvents,[{role:'managed-udp',kind:'exit',beforeOwnerReady:true,exitCode:7,signal:null}]);
 assert.equal(alive.listenerCount('error'),0);
 assert.equal(safePreparationDiagnostic({...error.networkPreparation,helperEvents:[{role:'private-secret',kind:'exit',beforeOwnerReady:true,exitCode:7,signal:null}]}),null);
 assert.equal(safePreparationDiagnostic({...error.networkPreparation,helperEvents:Array(5).fill(error.networkPreparation.helperEvents[0])}),null);
});

// Actual launch orchestration with real child processes; only namespace execution
// and the socket/file prerequisites are replaced. No listener or network service.
async function preparationLaunchFailure(mode) {
 const children=[];let relayClosed=0;
 const launchSource=source.slice(source.indexOf('export async function launchNativeNetwork(')).replace('export async function','async function');
 const stopChild=async child=>{
  if (!child || child.exitCode!==null || child.signalCode!==null || !child.pid) return;
  const exit=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');await exit;
 };
 const spawnOwned=(command)=>{
  let child;
  if(command==='unshare') child=spawn(process.execPath,['-e',"console.log('OVERTE_NET_OWNER_READY');setInterval(()=>{},1000)"],{stdio:['ignore','pipe','pipe']});
  else child=spawn('/not-present/private-helper-secret',[],{stdio:['ignore','pipe','pipe']});
  children.push(child);return child;
 };
 const launch=vm.runInNewContext(launchSource+';launchNativeNetwork',{
  path,net,process,JSON,Error,Promise,writeFile:async()=>{},owner:'fixed-owner',udpOwner:'fixed-udp',
  supervisorEnvironment:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin'},
  scopedNativeRelay:async()=>({close:async()=>{relayClosed++;}}),
  lineFrom,helperPreparationDiagnostics,stopChild
 });
 let failure;
 try {
  await launch({directory:'/owned-test',command:'bwrap',args:['--unshare-user','--'],env:{},hostPort:1,nativePath:'/native',spawnOwned,
   ...(mode==='udp'?{managedUDP:{address:'127.0.0.2',ports:[45102]}}:{})});
 } catch(error) {failure=error;}
 assert.ok(failure);assert.equal(relayClosed,1);
 for(const child of children)assert.ok(!child.pid || child.exitCode!==null || child.signalCode!==null);
 return failure;
}

test('actual production launch preserves slirp ENOENT through owner shutdown before native-ready', async()=>{
 const error=await preparationLaunchFailure('slirp');
 assert.equal(error.message,'Native network supervisor exited during preparation');
 assert.equal(error.networkPreparation.phase,'native-started');
 assert.equal(error.networkPreparation.category,'helper-spawn-failed');
 assert.deepEqual(error.networkPreparation.helperEvents,[{role:'slirp',kind:'spawn-error',beforeOwnerReady:false,errno:'ENOENT'}]);
 assert.equal(JSON.stringify(error.networkPreparation).includes('private-helper-secret'),false);
});

test('actual production launch diagnoses UDP spawn failure before owner allocation/readiness', async()=>{
 const error=await preparationLaunchFailure('udp');
 assert.equal(error.message,'Native network supervisor could not start');
 assert.equal(error.networkPreparation.phase,'udp-relay-ready');
 assert.equal(error.networkPreparation.category,'helper-spawn-failed');
 assert.deepEqual(error.networkPreparation.helperEvents,[{role:'managed-udp',kind:'spawn-error',beforeOwnerReady:true,errno:'ENOENT'}]);
});
