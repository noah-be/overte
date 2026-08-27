#!/usr/bin/env node
/*
 * One-shot out-of-band WDA runner background helper.
 *
 * XCTest normally sends a Home event while starting its UI-test runner.  On
 * affected physical devices that event can fail to complete and the runner
 * remains foreground until XCTest aborts with code 10300.  This helper waits
 * for the exact newly started, receipt-bound WDA process and sends exactly one
 * equivalent Home event through the independent RemoteXPC HID service.
 *
 * Private device/application identity is accepted only on stdin.  The Python
 * immutable-runtime wrapper suppresses dependency output, so this file emits
 * only fixed success/failure text of its own.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const MAX_INPUT = 4096;
const RUNNER_WAIT_MS = 22 * 1000;
const POLL_INTERVAL_MS = 100;
// Hardware spike: a 1500 ms settle survived the runner launch/rotation
// transition; the earlier Home event was lost during that transition.
const RUNNER_SETTLE_MS = 1500;
const BUNDLE_ID = /^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$/;

async function readRequest() {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_INPUT) throw new Error('invalid private WDA bootstrap request');
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks);
  const newline = raw.indexOf(0x0a);
  if (raw.includes(0x0d) || (newline >= 0 && newline !== raw.length - 1)) {
    throw new Error('private WDA bootstrap request must be one JSON line');
  }
  const value = JSON.parse(raw.toString('utf8'));
  if (!value || Object.keys(value).sort().join(',') !== 'schemaVersion,udid,wdaBundleId' ||
      value.schemaVersion !== 1 ||
      typeof value.udid !== 'string' || value.udid.length < 8 ||
      value.udid.length > 128 || /[\0\r\n]/.test(value.udid) ||
      typeof value.wdaBundleId !== 'string' || value.wdaBundleId.length > 255 ||
      !BUNDLE_ID.test(value.wdaBundleId)) {
    throw new Error('invalid private WDA bootstrap request');
  }
  return value;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function bounded(promise, deadline) {
  const remaining = Math.floor(deadline - performance.now());
  if (remaining <= 0) throw new Error('WDA runner wait expired');
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('WDA runner wait expired')), remaining);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

function exactRunnerPids(processes, executablePath) {
  if (!Array.isArray(processes)) throw new Error('invalid process inventory');
  const result = new Set();
  for (const process of processes) {
    const pid = process && process.processIdentifier;
    const relative = process && process.executableURL && process.executableURL.relative;
    if (relative === executablePath) {
      if (!Number.isSafeInteger(pid) || pid <= 0) {
        throw new Error('invalid WDA process identity');
      }
      result.add(pid);
    }
  }
  return result;
}

async function closeService(service) {
  if (service && typeof service.close === 'function') await service.close();
}

async function acquireService(start, deadline) {
  const pending = Promise.resolve().then(start);
  try {
    return await bounded(pending, deadline);
  } catch (error) {
    // A catalog lookup that resolves after our deadline must not leak the
    // newly constructed service.  Keep this rejection handler attached even
    // while the outer fail-closed path is unwinding.
    pending.then(closeService, () => {}).catch(() => {});
    throw error;
  }
}

async function main() {
  const request = await readRequest();
  const runtime = path.dirname(fs.realpathSync(__filename));
  const packageRoot = path.join(
    runtime, 'appium', 'node_modules', 'appium-ios-remotexpc'
  );
  const metadata = JSON.parse(fs.readFileSync(
    path.join(packageRoot, 'package.json'), 'utf8'
  ));
  if (metadata.name !== 'appium-ios-remotexpc' || metadata.version !== '5.15.3') {
    throw new Error('immutable RemoteXPC dependency mismatch');
  }
  const remoteXpc = await import(pathToFileURL(
    path.join(packageRoot, 'build', 'src', 'index.js')
  ).href);
  const services = remoteXpc.Services;
  if (!services || typeof services.startInstallationProxyService !== 'function' ||
      typeof services.startAppService !== 'function' ||
      typeof services.startHidIndigoService !== 'function') {
    throw new Error('required iOS RemoteXPC services are unavailable');
  }

  const deadline = performance.now() + RUNNER_WAIT_MS;
  let installationProxy;
  let appService;
  try {
    installationProxy = await acquireService(
      () => services.startInstallationProxyService(request.udid), deadline
    );
    const applications = await bounded(installationProxy.lookup(
      [request.wdaBundleId],
      {applicationType: 'User', returnAttributes: [
        'CFBundleIdentifier', 'CFBundleExecutable', 'ApplicationType', 'Path',
      ]},
    ), deadline);
    const application = applications && applications[request.wdaBundleId];
    if (!application || Object.keys(applications).length !== 1 ||
        application.CFBundleIdentifier !== request.wdaBundleId ||
        application.ApplicationType !== 'User' ||
        typeof application.CFBundleExecutable !== 'string' ||
        !/^[A-Za-z0-9_.-]+$/.test(application.CFBundleExecutable) ||
        !application.CFBundleExecutable.endsWith('-Runner') ||
        typeof application.Path !== 'string' || !application.Path.startsWith('/') ||
        !application.Path.endsWith('.app') ||
        path.posix.normalize(application.Path) !== application.Path ||
        /[\0\r\n]/.test(application.Path + application.CFBundleExecutable)) {
      throw new Error('installed WDA runner identity is invalid');
    }
    const executablePath = path.posix.join(
      application.Path, application.CFBundleExecutable
    );

    appService = await acquireService(
      () => services.startAppService(request.udid), deadline
    );
    const baseline = exactRunnerPids(
      await bounded(appService.listProcesses(), deadline), executablePath
    );
    // The caller must not start Appium before this line.  Otherwise a freshly
    // launched runner could be mistaken for a baseline process.
    process.stdout.write('READY\n');
    let runnerPid;
    while (performance.now() < deadline) {
      const current = exactRunnerPids(
        await bounded(appService.listProcesses(), deadline), executablePath
      );
      const newRunnerPids = [...current].filter((pid) => !baseline.has(pid));
      if (newRunnerPids.length > 1) {
        throw new Error('multiple new WDA runners appeared');
      }
      if (newRunnerPids.length === 1) {
        [runnerPid] = newRunnerPids;
        break;
      }
      await bounded(delay(POLL_INTERVAL_MS), deadline);
    }
    if (runnerPid === undefined) throw new Error('new WDA runner did not appear');

    await bounded(delay(RUNNER_SETTLE_MS), deadline);
    const settled = exactRunnerPids(
      await bounded(appService.listProcesses(), deadline), executablePath
    );
    const settledNewRunnerPids = [...settled].filter((pid) => !baseline.has(pid));
    if (settledNewRunnerPids.length !== 1 || settledNewRunnerPids[0] !== runnerPid) {
      throw new Error('new WDA runner identity became ambiguous before recovery');
    }

    let hidService;
    try {
      // Starting this service is also the fail-closed iOS/feature-catalog gate.
      hidService = await acquireService(
        () => services.startHidIndigoService(request.udid), deadline
      );
      if (!hidService || typeof hidService.pressButton !== 'function') {
        throw new Error('iOS HID Home service is unavailable');
      }
      await bounded(hidService.pressButton('home', {pressCount: 1}), deadline);
    } finally {
      await closeService(hidService);
    }
  } finally {
    try {
      await closeService(appService);
    } finally {
      await closeService(installationProxy);
    }
  }
}

main().then(
  () => process.stdout.write('PASS\n'),
  () => {
    process.stderr.write('error: WDA runner background recovery failed\n');
    process.exitCode = 2;
  },
);
