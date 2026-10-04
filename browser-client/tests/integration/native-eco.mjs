// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// A strictly owned fresh normal native process; opt-in ECO0 A/B experiment.
// No entity, graphics, LOD, microphone or performance-preset setter runs.
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';

const args = process.argv.slice(2), repoOption = args.indexOf('--repo');
assert(args.length === 0 || (args.length === 2 && repoOption === 0), 'Only the reviewed repo option is accepted');
const repo = repoOption >= 0 ? path.resolve(args[repoOption + 1]) : path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const packageDirectory = path.join(repo, 'browser-client'), lab = path.join(repo, 'build/browser-lab');
const run = randomUUID(), output = path.join(lab, 'evidence/native-eco', run), profile = path.join(output, 'profile');
const domain = 'overte://127.0.0.2:45102', marker = 'OVERTE_BROWSER_NATIVE_ECO ';
const report = { startedAt: new Date().toISOString(), completed: false,
  scope: 'Fresh standalone normal native profile with one ECO0 setter and original-profile restoration; not a sandboxed gateway worker or Tablet/audio/pose acceptance',
  entityWrites: 0, microphoneRequested: false, experimentalEcoOptIn: process.env.OVERTE_LAB_NATIVE_ECO === '1',
  productionDefaultEnabled: false, records: [], cpuSamples: {}, nativeQualityCaptureVerified: false,
  tabletAudioPoseAcceptanceVerified: false, identicalActualLODOrWorkloadVerified: false };
const sourceFiles = ['gateway/server.mjs', 'tests/integration/native-eco.mjs', 'tests/integration/native-eco-probe.js'];
const phases = new Set(), measurements = [];
let native, rejection, exit;
const carries = { stdout: '', stderr: '' };
let ownedLeader;
const ownedMembers = new Map();
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function safeFailure(error) {
  // Native stderr, filesystem error messages and arbitrary assertion operands
  // may contain paths. Only reviewed assertion captions or bounded codes escape.
  if (error?.code === 'ERR_ASSERTION') return 'A native ECO proof assertion failed';
  if (/^(?:ENOENT|EACCES|EPERM|ESRCH|EIO)$/.test(error?.code)) return 'Owned proof operation failed: ' + error.code;
  const message = String(error?.message || 'Owned native refresh proof failed');
  return /^[A-Za-z0-9 ,.\-:]+$/.test(message) && message.length <= 200 ? message : 'Owned native refresh proof failed';
}
async function hashes() { return Object.fromEntries(await Promise.all(sourceFiles.map(async file => [file, sha(await readFile(path.join(packageDirectory, file)))]))); }
async function waitFor(predicate, label, timeout = 90000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (rejection) throw rejection;
    if (native && (native.exitCode !== null || native.signalCode !== null)) throw Error('The owned native process exited before the native ECO proof completed');
    if (await predicate()) return;
    await delay(100);
  }
  throw Error(label + ' exceeded the bounded native startup deadline');
}
function validateRecord(value) {
  assert(value && typeof value === 'object' && !Array.isArray(value), 'Native ECO record must be an object');
  assert(Number.isSafeInteger(value.at) && value.at > 0, 'Native record needs its actual timestamp');
  if (value.phase === 'error' || value.phase === 'restoreError') throw Error('Native ECO experiment rejected its API connection or quality contract');
  const allowed = ['phase','at','nativeVersion','connected','domainMatched','refreshRateProfile','regime','targetHz','quality','dynamicLOD'];
  assert.deepEqual(Object.keys(value).sort(), allowed.sort(), 'Only reviewed native record fields are admitted');
  assert(['baseline','baselineEnd','eco','ecoEnd','restored'].includes(value.phase), 'Native phase must be reviewed');
  assert.equal(value.nativeVersion,'2026.04.1');assert.equal(value.connected,true);assert.equal(value.domainMatched,true);
  assert(Number.isSafeInteger(value.refreshRateProfile)&&value.refreshRateProfile>=0&&value.refreshRateProfile<=2);
  assert(Number.isSafeInteger(value.regime)&&value.regime>=0&&value.regime<=3);
  assert(Number.isSafeInteger(value.targetHz)&&value.targetHz>=1&&value.targetHz<=1000);
  const q=value.quality;
  const fields=['performancePreset','renderMethod','shadowsEnabled','hazeEnabled','bloomEnabled','ambientOcclusionEnabled','localLightingEnabled','proceduralMaterialsEnabled','antialiasingMode','viewportResolutionScale','verticalFieldOfView','cameraClippingEnabled','worldDetailQuality','automaticLODAdjust'];
  assert(q&&typeof q==='object'&&!Array.isArray(q));assert.deepEqual(Object.keys(q).sort(),fields.sort());
  for(const field of ['shadowsEnabled','hazeEnabled','bloomEnabled','ambientOcclusionEnabled','localLightingEnabled','proceduralMaterialsEnabled','cameraClippingEnabled','automaticLODAdjust'])assert.equal(typeof q[field],'boolean');
  for(const field of ['performancePreset','renderMethod','antialiasingMode','worldDetailQuality'])assert(Number.isSafeInteger(q[field]));
  assert(q.performancePreset>=1&&q.performancePreset<=4);assert(q.renderMethod>=0&&q.renderMethod<=1);assert(q.antialiasingMode>=0&&q.antialiasingMode<=32);assert(q.worldDetailQuality>=0&&q.worldDetailQuality<=2);
  assert(Number.isFinite(q.viewportResolutionScale)&&q.viewportResolutionScale>=.001&&q.viewportResolutionScale<=100);
  assert(Number.isFinite(q.verticalFieldOfView)&&q.verticalFieldOfView>=.001&&q.verticalFieldOfView<=179.999);
  assert(value.dynamicLOD&&typeof value.dynamicLOD==='object'&&!Array.isArray(value.dynamicLOD));assert.deepEqual(Object.keys(value.dynamicLOD).sort(),['angleDeg','targetFPS']);
  assert(Number.isFinite(value.dynamicLOD.angleDeg)&&value.dynamicLOD.angleDeg>=0&&value.dynamicLOD.angleDeg<=180);
  assert(Number.isFinite(value.dynamicLOD.targetFPS)&&value.dynamicLOD.targetFPS>=.001&&value.dynamicLOD.targetFPS<=1000);
  if(value.phase==='eco'||value.phase==='ecoEnd'){assert.equal(value.refreshRateProfile,0);assert.equal(value.targetHz,[20,10,5,2][value.regime]);}
  return value;
}
function consume(stream, chunk) {
  let carry = carries[stream] + chunk.toString();
  for (;;) {
    const newline = carry.indexOf('\n'); if (newline < 0) break;
    const line = carry.slice(0, newline); carry = carry.slice(newline + 1);
    const offset = line.indexOf(marker); if (offset < 0) continue;
    try { assert(line.length < 8192, 'Native record exceeds its byte bound'); assert(report.records.length < 5, 'More than five native phase records');
      const record=validateRecord(JSON.parse(line.slice(offset + marker.length)));assert(!phases.has(record.phase), 'Native phase may only occur once');phases.add(record.phase);report.records.push(record);
      if(record.phase==='baseline'||record.phase==='eco')measurements.push(sampleCPU(record.phase).catch(error=>{rejection=error;}));
    } catch (error) { rejection = error; }
  }
  // Native logs are discarded; retain only a bounded incomplete line locally.
  if (carry.length > 65536) carry = carry.slice(-65536);
  carries[stream] = carry;
}
function parseProc(value) {
  const fields = value.slice(value.lastIndexOf(')') + 2).trim().split(/\s+/);
  // fields[0] is Linux stat field3/state, so utime14/stime15 are11/12.
  const pid = Number(value.slice(0, value.indexOf(' '))), group = Number(fields[2]), session = Number(fields[3]);
  const user = Number(fields[11]), system = Number(fields[12]), start = Number(fields[19]);
  assert([pid, group, session, user, system, start].every(Number.isSafeInteger));
  return { pid, group, session, state: fields[0], ticks: user + system, start };
}
async function proc(pid) {
  try { return parseProc(await readFile(`/proc/${pid}/stat`, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT' || error.code === 'ESRCH') return null; throw error; }
}
async function cpu(pid) {
  const value = await proc(pid); assert(value, 'Owned CPU process must still exist'); return { ticks: value.ticks, start: value.start };
}
function sameLeader(value) { return value && value.pid === ownedLeader.pid && value.start === ownedLeader.start
  && value.group === ownedLeader.group && value.session === ownedLeader.session; }
async function members() {
  const names = (await readdir('/proc')).filter(name => /^\d+$/.test(name));
  if (names.length > 65536) throw Error('Owned group inspection exceeds its bounded process budget');
  const found = [];
  for (let offset = 0; offset < names.length; offset += 32) {
    const batch = await Promise.all(names.slice(offset, offset + 32).map(name => proc(Number(name))));
    for (const value of batch) if (value?.group === ownedLeader.group) found.push(value);
  }
  return found;
}
async function inspectOwnedGroup() {
  if (!ownedLeader) return [];
  const leader = await proc(ownedLeader.pid);
  if (leader && !sameLeader(leader)) throw Error('Owned native leader identity changed; signaling refused');
  const current = await members();
  // Recheck after enumeration. A live leader authorizes recording members of
  // its original SID/PGRP; after it exits, every remaining member must already
  // have an independently captured original starttime and session identity.
  const again = await proc(ownedLeader.pid);
  if (again && !sameLeader(again)) throw Error('Owned native leader identity changed; signaling refused');
  if (again) {
    for (const value of current) {
      if (value.session !== ownedLeader.session) throw Error('Owned native group session changed; signaling refused');
      ownedMembers.set(value.pid, value.start);
    }
  } else {
    for (const value of current) if (value.session !== ownedLeader.session || ownedMembers.get(value.pid) !== value.start)
      throw Error('Unverified native group member remains; signaling refused');
  }
  return current;
}
async function signalOwned(signal) {
  const current = await inspectOwnedGroup(); if (!current.length) return false;
  // Final ownership check immediately before the synchronous syscall. There
  // is no await between that last identity comparison and group signaling.
  const leader = await proc(ownedLeader.pid);
  if (leader) { if (!sameLeader(leader)) throw Error('Owned native leader identity changed; signaling refused'); }
  else {
    const anchor = current.find(value => ownedMembers.get(value.pid) === value.start && value.state !== 'Z');
    if (!anchor) throw Error('No live recorded owned group anchor remains; signaling refused');
    const checked = await proc(anchor.pid);
    if (!checked || checked.start !== anchor.start || checked.group !== ownedLeader.group || checked.session !== ownedLeader.session)
      throw Error('Recorded native group anchor changed; signaling refused');
  }
  try { process.kill(-ownedLeader.group, signal); } catch (error) { if (error.code !== 'ESRCH') throw error; }
  return true;
}
async function stopOwned() {
  if (!native || !Number.isSafeInteger(native.pid)) return { started: false, processExited: true, groupExited: true };
  if (!ownedLeader) throw Error('Native leader ownership was not captured; signaling refused');
  for (const signal of ['SIGTERM', 'SIGKILL']) {
    if (!(await signalOwned(signal))) break;
    const end = Date.now() + 3000;
    while ((await inspectOwnedGroup()).length && Date.now() < end) await delay(100);
  }
  return { started: true, processExited: native.exitCode !== null || native.signalCode !== null,
    groupExited: (await inspectOwnedGroup()).length === 0, identityGuarded: true, exit };
}
async function sampleCPU(phase) {
  const before=await cpu(native.pid),start=process.hrtime.bigint(),startedAt=new Date().toISOString();
  assert.equal(before.start,ownedLeader.start,'The sampled process must retain its recorded original identity');
  await delay(3000);const after=await cpu(native.pid),seconds=Number(process.hrtime.bigint()-start)/1e9;
  assert.equal(before.start,after.start,'The sampled owned PID must retain its identity');assert(after.ticks>=before.ticks);
  report.cpuSamples[phase]={startedAt,finishedAt:new Date().toISOString(),seconds,
    processCpuSeconds:(after.ticks-before.ticks)/clockTicks,meanProcessCores:(after.ticks-before.ticks)/clockTicks/seconds,
    scope:'Owned Interface leader only; no descendant sum or identical workload claim'};
}
let clockTicks;
try {
  // Refuse before any profile allocation or process launch. This does not set a
  // gateway environment flag and cannot alter an existing native participant.
  assert.equal(process.env.OVERTE_LAB_NATIVE_ECO,'1','Explicit standalone ECO opt-in is required');
  report.startSourceSHA256=await hashes();
  const server=await readFile(path.join(packageDirectory,'gateway/server.mjs'),'utf8');
  const match=/await writeFile\(path\.join\(settingsDirectory, 'Interface\.json'\), JSON\.stringify\(\{([\s\S]*?)\}\), \{ mode: 0o600 \}\);/.exec(server);
  assert(match,'Use the actual reviewed production private worker payload');
  const settings=vm.runInNewContext(`(function(){return {${match[1]}};}).call({input:'lab_input',output:'lab_output'})`,{process:{env:{}}});
  assert.deepEqual(JSON.parse(JSON.stringify(settings)),{'Audio/Desktop/INPUT':'lab_input.monitor','Audio/Desktop/OUTPUT':'lab_output','Audio/mutedDesktop':true,firstRun:false,viewportResolutionScale:.1},'Normal private startup payload must remain unchanged');
  report.productionSettingsSHA256=sha(Buffer.from(JSON.stringify(settings)));
  await mkdir(path.join(profile,'config/Overte'),{recursive:true,mode:0o700});
  await writeFile(path.join(profile,'config/Overte/Interface.json'),JSON.stringify(settings),{mode:0o600});
  const script=await readFile(path.join(packageDirectory,'tests/integration/native-eco-probe.js'),'utf8');
  const scriptFile=path.join(profile,'probe.js');await writeFile(scriptFile,script,{mode:0o600});report.trustedScriptSHA256=sha(Buffer.from(script));
  const binary=path.join(lab,'appimage/squashfs-root/usr/bin/interface');report.nativeBinarySHA256=sha(await readFile(binary));
  const tickResult=spawnSync('getconf',['CLK_TCK'],{encoding:'utf8'});clockTicks=Number(tickResult.stdout.trim());
  assert.equal(tickResult.status,0);assert(Number.isSafeInteger(clockTicks)&&clockTicks>0);
  native=spawn(path.join(lab,'appimage/squashfs-root/AppRun'),['--url',domain.replace('overte:','hifi:'),'--allowMultipleInstances','--no-updater','--no-login-suggestion','--suppress-settings-reset','--disableDisplayPlugins','OpenXR,OpenVR','--defaultScriptsOverride',pathToFileURL(scriptFile).href],
    {detached:true,env:{...process.env,DISPLAY:':95',QT_QPA_PLATFORM:'xcb',QT_SCALE_FACTOR:'1',QT_AUTO_SCREEN_SCALE_FACTOR:'0',PULSE_SERVER:`unix:${lab}/runtime/native-pulse.sock`,XDG_CONFIG_HOME:path.join(profile,'config'),XDG_CACHE_HOME:path.join(profile,'cache'),XDG_DATA_HOME:path.join(profile,'data')},stdio:['ignore','pipe','pipe']});
  native.on('error',error=>{rejection=Error('The owned native process could not start: '+error.code);});native.once('exit',(code,signal)=>{exit={code,signal};});
  native.stdout.on('data',chunk=>consume('stdout',chunk));native.stderr.on('data',chunk=>consume('stderr',chunk));
  const leader=await proc(native.pid);assert(leader&&leader.group===native.pid&&leader.session===native.pid,'Fresh detached native leader identity is required');
  ownedLeader=leader;ownedMembers.set(leader.pid,leader.start);await inspectOwnedGroup();report.launchedAt=new Date().toISOString();
  await waitFor(()=>report.records.length===5,'Five actual native ECO phase records',105000);await Promise.all(measurements);if(rejection)throw rejection;
  assert.deepEqual(report.records.map(r=>r.phase),['baseline','baselineEnd','eco','ecoEnd','restored'],'Native phases retain their causal ordering');
  const [before,beforeEnd,eco,ecoEnd,restored]=report.records;
  for(const record of report.records){assert.deepEqual(record.quality,before.quality,'Configured native quality must remain unchanged');assert.equal(record.regime,before.regime,'Refresh regime must remain unchanged across the A B windows');}
  assert.equal(beforeEnd.refreshRateProfile,before.refreshRateProfile);assert.equal(restored.refreshRateProfile,before.refreshRateProfile);
  assert(beforeEnd.at-before.at>=4900&&ecoEnd.at-eco.at>=4900,'Each native observation phase retains its five second interval');
  assert(report.cpuSamples.baseline&&report.cpuSamples.eco,'Both real three second CPU windows completed');
  assert(Date.parse(report.cpuSamples.baseline.finishedAt)<=eco.at&&Date.parse(report.cpuSamples.eco.finishedAt)<=restored.at,'CPU windows must not overlap native phase transitions');
  report.baselineAlreadyEco=before.refreshRateProfile===0;report.configuredQualityUnchanged=true;
  report.effectiveLODTargetChanged=before.dynamicLOD.targetFPS!==eco.dynamicLOD.targetFPS;
  report.sourceBoundNativeSetterAndCPUProof=true;report.completed=true;
} catch (error) { report.error = safeFailure(error); process.exitCode = 1; }
finally {
  await Promise.all(measurements);
  try { report.processCleanup = await stopOwned(); if (!report.processCleanup.processExited || !report.processCleanup.groupExited) throw Error('An owned native process/group remains'); }
  catch (error) { report.cleanupError = safeFailure(error); report.completed = false; process.exitCode = 1; }
  carries.stdout = ''; carries.stderr = '';
  if (report.processCleanup?.groupExited) {
    try { await rm(profile, { recursive: true, force: true }); report.privateProfileRemoved = true; }
    catch (error) { report.privateProfileRemoved = false; report.cleanupError = safeFailure(error); report.completed = false; process.exitCode = 1; }
  } else report.privateProfileRemoved = false;
  try { report.sourceSHA256 = await hashes(); report.sourceCoherent = JSON.stringify(report.startSourceSHA256) === JSON.stringify(report.sourceSHA256);
    if (!report.sourceCoherent) { report.completed = false; report.error ||= 'Source changed during the native ECO proof'; process.exitCode = 1; }
  } catch { report.completed = false; report.sourceCoherent = false; process.exitCode = 1; }
  report.finishedAt = new Date().toISOString(); await mkdir(output, { recursive: true, mode: 0o700 });
  await writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
  console.log(JSON.stringify(report));
}
