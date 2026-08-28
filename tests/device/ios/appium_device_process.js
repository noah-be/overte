#!/usr/bin/env node
/*
 * Exact, WDA-independent iOS application termination helper.
 *
 * The device and bundle identities arrive only on stdin.  Successful output
 * contains no private values.  The immutable Python wrapper also suppresses
 * library diagnostics because RemoteXPC errors may contain hardware data.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const MAX_INPUT = 4096;
const BUNDLE_ID = /^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$/;

async function readRequest() {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_INPUT) throw new Error('invalid private process request');
    chunks.push(chunk);
  }
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!request || Object.keys(request).sort().join(',') !== 'bundleId,udid' ||
      typeof request.udid !== 'string' || request.udid.length < 8 ||
      request.udid.length > 128 || /[\0\r\n]/.test(request.udid) ||
      typeof request.bundleId !== 'string' || request.bundleId.length > 255 ||
      !BUNDLE_ID.test(request.bundleId)) {
    throw new Error('invalid private process request');
  }
  return request;
}

const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

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
  const dvt = await remoteXpc.Services.startDVTService(request.udid);
  try {
    const pid = await dvt.processControl.getPidForBundleIdentifier(request.bundleId);
    if (pid) await dvt.processControl.kill(pid);
    for (let attempt = 0; attempt < 50; ++attempt) {
      if (!await dvt.processControl.getPidForBundleIdentifier(request.bundleId)) return;
      await pause(100);
    }
    throw new Error('application remained running');
  } finally {
    await dvt.dvtService.close();
  }
}

main().then(
  () => process.stdout.write('PASS: iOS application is not running\n'),
  () => {
    process.stderr.write('error: private iOS application termination failed\n');
    process.exitCode = 2;
  },
);
