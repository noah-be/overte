#!/usr/bin/env node
/* Replace the two receipt-verified signed apps. Emits no private metadata. */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const MAX_INPUT = 8192;
const OVERTE_ID = 'org.overte.interface.e2e';
const WDA_ID = 'org.overte.WebDriverAgentRunner.xctrunner';

async function readRequest() {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_INPUT) throw new Error('invalid private install request');
    chunks.push(chunk);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!value || Object.keys(value).sort().join(',') !== 'overteIpa,udid,wdaIpa' ||
      typeof value.udid !== 'string' || value.udid.length < 8 || value.udid.length > 128 ||
      typeof value.overteIpa !== 'string' || typeof value.wdaIpa !== 'string' ||
      /[\0\r\n]/.test(value.udid + value.overteIpa + value.wdaIpa)) {
    throw new Error('invalid private install request');
  }
  return value;
}

async function main() {
  const request = await readRequest();
  const runtime = path.dirname(fs.realpathSync(__filename));
  const realDevicePath = path.join(
    runtime, 'appium', 'node_modules', 'appium-xcuitest-driver', 'build', 'lib',
    'device', 'real-device-management.js'
  );
  const {RealDevice} = await import(pathToFileURL(realDevicePath).href);
  const quiet = {info() {}, debug() {}, warn() {}, error() {}};
  const device = new RealDevice(request.udid, {}, quiet);
  const apps = [[OVERTE_ID, request.overteIpa], [WDA_ID, request.wdaIpa]];
  try {
    for (const [bundle] of apps) {
      if (await device.isAppInstalled(bundle)) await device.removeApp(bundle);
    }
    await device.installApp(request.wdaIpa, WDA_ID, {timeoutMs: 8 * 60 * 1000});
    await device.installApp(request.overteIpa, OVERTE_ID, {timeoutMs: 8 * 60 * 1000});
  } catch (error) {
    for (const [bundle] of apps) {
      try {
        if (await device.isAppInstalled(bundle)) await device.removeApp(bundle);
      } catch (_) {}
    }
    throw error;
  }
}

main().then(
  () => process.stdout.write('PASS: signed iOS apps installed\n'),
  () => {
    process.stderr.write('error: signed iOS app installation failed\n');
    process.exitCode = 2;
  },
);
