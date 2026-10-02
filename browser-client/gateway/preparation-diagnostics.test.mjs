// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { spawn, spawnSync } from 'node:child_process';
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


// Import the actual Python owner without launching its namespace/native main.
// Only the existing route-command call is controlled; its exception identity,
// fixed stderr marker and unchanged route arguments are exercised directly.
function actualRouteOwner(program) {
 const result = spawnSync('python3', ['-c', `
import contextlib, importlib.util, io, json, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('tested_network_owner',root/'network-owner.py')
owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
${program}
`, path.dirname(new URL(import.meta.url).pathname)], {encoding:'utf8',timeout:3000,maxBuffer:65536});
 assert.equal(result.error, undefined);assert.equal(result.status,0,'Controlled route-owner test must complete');
 return JSON.parse(result.stdout);
}

test('actual route installation preserves all denied routes and original failure while forwarding fixed errno',()=>{
 const outputs=actualRouteOwner(`
records=[]
for stderr in [b'RTNETLINK answers: Operation not permitted\\nprivate-token /private/path',
               b'private-token: Operation not permitted',
               b'x'*4096+b'\\nRTNETLINK answers: File exists',
               b'RTNETLINK answers: No buffer space available\\n']:
 error=subprocess.CalledProcessError(2,['ip','route','add','prohibit','private-route'],stderr=stderr)
 calls=[]
 def fail(args,**kwargs):
  calls.append([args,kwargs]);raise error
 owner.subprocess.run=fail
 stream=io.StringIO()
 with contextlib.redirect_stderr(stream):
  try: owner.install_denied_routes()
  except subprocess.CalledProcessError as observed: same=observed is error
 records.append({'same':same,'calls':calls,'marker':stream.getvalue()})
success=[]
owner.subprocess.run=lambda args,**kwargs:success.append([args,kwargs])
owner.install_denied_routes()
print(json.dumps({'records':records,'success':success}))
`);
 assert.equal(outputs.success.length,12);
 assert.deepEqual(outputs.success.map(call=>call[0]),[
  '10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','100.64.0.0/10','192.0.0.0/24',
  '192.0.2.0/24','198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4'
 ].map(route=>['ip','route','add','prohibit',route]));
 for(const call of outputs.success)assert.deepEqual(call[1],{check:true,capture_output:true});
 const expected=['permission-denied','unclassified-route-error','unclassified-route-error','kernel-resource-unavailable'];
 for(let i=0;i<outputs.records.length;i++){
  const value=outputs.records[i];assert.equal(value.same,true);assert.equal(value.calls.length,1);
  assert.equal(value.marker.includes('private'),false);
  const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');
  // Split the actual Python-produced marker to exercise pipe fragmentation.
  const bytes=Buffer.from(value.marker);d.observe(bytes.subarray(0,17));d.observe(bytes.subarray(17));
  d.observe(Buffer.from("Private native network failed: Command '['ip', 'route', 'add', 'prohibit', 'fixed-route']' returned non-zero exit status 2.\n"));
  const out=d.snapshot(1,null);assert.equal(out.category,'deny-route-command-failed');
  assert.equal(out.routeFailure.category,expected[i]);assert.equal(out.routeFailure.exitCode,2);
  assert.equal(out.routeFailure.truncated,i===2);assert.ok(Object.isFrozen(out.routeFailure));
  assert.deepEqual(safePreparationDiagnostic(out),out);
 }
});

test('route diagnostic forwarding rejects forged enum/counters and strips arbitrary fields',()=>{
 const base=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED').snapshot(1,null);
 const route={category:'permission-denied',stderrBytes:42,truncated:false,exitCode:2};
 assert.deepEqual(safePreparationDiagnostic({...base,routeFailure:{...route,raw:'private-secret'}}).routeFailure,route);
 for(const patch of [{category:'private-secret'},{stderrBytes:-1},{stderrBytes:1.5},{stderrBytes:Number.MAX_SAFE_INTEGER+1},
  {truncated:1},{exitCode:256},{exitCode:'2'}]){
  assert.equal(safePreparationDiagnostic({...base,routeFailure:{...route,...patch}}),null);
  const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from('OVERTE_NET_ROUTE_FAILURE='+JSON.stringify({...route,...patch})+'\n'));
  assert.equal(d.snapshot(1,null).routeFailure,undefined);
 }
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from('OVERTE_NET_ROUTE_FAILURE={"private":"secret"}\n'));
 assert.equal(d.snapshot(1,null).routeFailure,undefined);
});

test('route refusal preserves a bounded fixed owner-context projection without raw profiles or namespace IDs',()=>{
 const ownerContext={profile:'unshare-unpriv',capabilitySets:{inheritable:'zero',permitted:'nonzero',effective:'nonzero',bounding:'nonzero',ambient:'zero'},netAdmin:{permitted:'present',effective:'present',bounding:'present'},namespaceRelations:{user:'different-from-visible-pid1',net:'different-from-visible-pid1'},raw:'private-secret'};
 const route={category:'permission-denied',stderrBytes:43,truncated:false,exitCode:2,ownerContext};
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from('OVERTE_NET_ROUTE_FAILURE='+JSON.stringify(route)+'\n'));
 const out=d.snapshot(1,null);assert.equal(out.routeFailure.ownerContext.profile,'unshare-unpriv');assert.ok(!JSON.stringify(out).includes('private-secret'));
 assert.deepEqual(safePreparationDiagnostic(out).routeFailure.ownerContext,out.routeFailure.ownerContext);
 assert.ok(Object.isFrozen(out.routeFailure.ownerContext.capabilitySets));
 for(const change of [{profile:'private-secret'},{netAdmin:{...ownerContext.netAdmin,effective:true}},{capabilitySets:{...ownerContext.capabilitySets,effective:'1000'}},{namespaceRelations:{...ownerContext.namespaceRelations,net:'net:[100]'}}]){
  const broken={...route,ownerContext:{...ownerContext,...change}};assert.equal(safePreparationDiagnostic({...out,routeFailure:broken}),null);
  const observation=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');observation.observe(Buffer.from('OVERTE_NET_ROUTE_FAILURE='+JSON.stringify(broken)+'\n'));
  assert.equal(observation.snapshot(1,null).routeFailure,undefined);
 }
});

test('pre-route proc observations and actual unchanged route function pass portable Python contracts',()=>{
 const result=spawnSync('python3',['-m','unittest','-q','test_network_owner_context'],{
  cwd:new URL('.',import.meta.url),encoding:'utf8',timeout:2000,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 assert.equal(result.status,0, result.error?.code || 'Bounded fixed owner-context contracts failed');
 assert.match(result.stderr,/Ran 4 tests/);
});
