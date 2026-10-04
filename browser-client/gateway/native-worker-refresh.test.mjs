// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const server = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
const match = /await writeFile\(path\.join\(settingsDirectory, 'Interface\.json'\), JSON\.stringify\(\{([\s\S]*?)\}\), \{ mode: 0o600 \}\);/.exec(server);
assert.ok(match, 'Exercise the actual private worker settings payload');
function settings(flag='1') { return vm.runInNewContext(`(function(){return {${match[1]}};}).call({input:'owned_input',output:'owned_output'})`,{process:{env:{OVERTE_GATEWAY_NATIVE_REFRESH_QOS:flag}}}); }
const reader = vm.runInNewContext(`${await readFile(new URL('./native-worker-refresh-readback.js', import.meta.url), 'utf8')}\nreadNativeWorkerRefresh;`);
const rates = [10, 10, 10, 2, 10, 30];
function api(options = {}) {
  const calls = [], value = { getPerformancePreset: () => 5, getRefreshRateProfile: () => 3,
    getRefreshRateRegime: () => 0, getActiveRefreshRate: () => 10,
    getCustomRefreshRate: index => { calls.push(index); return rates[index]; }, ...options };
  return { value, calls };
}

test('actual private settings preserve audio/mute/viewport and initialize Custom before auto-performance selection', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(settings())), {
    'Audio/Desktop/INPUT': 'owned_input.monitor', 'Audio/Desktop/OUTPUT': 'owned_output',
    'Audio/mutedDesktop': true, firstRun: false, viewportResolutionScale: .1,
    performancePreset: 5, refreshRateProfile: 3,
    customRefreshRateFocusActive: 10, customRefreshRateFocusInactive: 10,
    customRefreshRateUnfocus: 10, customRefreshRateMinimized: 2,
    customRefreshRateStartup: 10, customRefreshRateShutdown: 30,
  });
});

test('normal startup preserves prior native defaults and unapproved experiment flag values do not activate QoS',()=>{
  for(const flag of [undefined,'','0','true','2'])assert.deepEqual(JSON.parse(JSON.stringify(settings(flag===undefined ? '' : flag))),{
    'Audio/Desktop/INPUT':'owned_input.monitor','Audio/Desktop/OUTPUT':'owned_output',
    'Audio/mutedDesktop':true,firstRun:false,viewportResolutionScale:.1,
  });
});

test('trusted native readback verifies all six bounded regime settings and the actually selected target', () => {
  for (let regime = 0; regime < 6; regime++) {
    const f = api({ getRefreshRateRegime: () => regime, getActiveRefreshRate: () => rates[regime] });
    const result = reader(f.value); assert.equal(result.applied, true); assert.equal(result.targetHz, rates[regime]);
    assert.deepEqual(f.calls, [0, 1, 2, 3, 4, 5]);
    assert.ok(result.scope.includes('actual frame cadence')); assert.equal(Object.keys(result).some(key => /device|label|path|name|url/i.test(key)), false);
  }
});

test('source reset, profile mismatch and changed custom targets remain explicit non-applied results', () => {
  for (const change of [
    { getPerformancePreset: () => 3 }, { getRefreshRateProfile: () => 2 },
    { getActiveRefreshRate: () => 60 }, { getCustomRefreshRate: () => 20 },
  ]) assert.equal(reader(api(change).value).applied, false);
});

test('missing/invalid native APIs fail diagnostically without mutating worker or visitor state', () => {
  for (const value of [undefined, {}, { ...api().value, getCustomRefreshRate: null }]) assert.throws(() => reader(value), /unavailable/);
  for (const value of [undefined, null, '10', NaN, Infinity, -1, 0, 1001, 10.5]) {
    assert.throws(() => reader(api({ getActiveRefreshRate: () => value }).value), /invalid/);
    assert.throws(() => reader(api({ getCustomRefreshRate: () => value }).value), /invalid/);
  }
  const f = api({ setRefreshRateProfile() { throw Error('No native setter may run'); }, setPerformancePreset() { throw Error('No graphics setter may run'); } });
  assert.equal(reader(f.value).applied, true);
});

test('optional actual probe source emits at most six sanitized records and clears its timer on completion/teardown', async () => {
  const logs = [], cleared = [], handle = Object.freeze({}); let tick, ending;
  const Script = { setInterval(callback, interval) { assert.equal(interval, 1000); tick = callback; return handle; },
    clearInterval(value) { assert.equal(value, handle); cleared.push(value); }, scriptEnding: { connect(callback) { ending = callback; } } };
  vm.runInNewContext(await readFile(new URL('./native-worker-refresh-probe.js', import.meta.url), 'utf8'), {
    Script, Performance: api().value, readNativeWorkerRefresh: reader, print: value => logs.push(value),
  });
  assert.equal(typeof tick, 'function'); for (let i = 0; i < 6; i++) tick();
  assert.equal(logs.length, 6); assert.equal(cleared.length, 1); ending(); assert.equal(cleared.length, 2);
  for (const line of logs) { const value = JSON.parse(line.slice('OVERTE_BROWSER_WORKER_REFRESH '.length)); assert.equal(value.applied, true); assert.ok(Number.isFinite(value.at)); }
});
