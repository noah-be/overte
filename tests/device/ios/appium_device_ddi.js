#!/usr/bin/env node
/*
 * Strict Personalized Developer Disk Image mount/status helper.
 *
 * The private device identity and Apple payload paths are accepted only on
 * stdin.  The Python immutable-runtime wrapper suppresses all library output,
 * because RemoteXPC/TSS diagnostics can contain hardware identifiers and
 * nonces.  This helper therefore emits no success payload of its own.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const MAX_INPUT = 16 * 1024;
const SERVICES = [
  'com.apple.dt.testmanagerd.remote',
  'com.apple.instruments.dtservicehub',
];
const SHA384 = /^[0-9a-f]{96}$/;

async function readRequest() {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_INPUT) throw new Error('invalid private DDI request');
    chunks.push(chunk);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!value || typeof value.udid !== 'string' || value.udid.length < 8 ||
      value.udid.length > 128 || /[\0\r\n]/.test(value.udid) ||
      !['mount', 'status'].includes(value.action) ||
      typeof value.imageSha384 !== 'string' || !SHA384.test(value.imageSha384)) {
    throw new Error('invalid private DDI request');
  }
  const keys = Object.keys(value).sort().join(',');
  if (value.action === 'status' && keys === 'action,imageSha384,udid') return value;
  if (value.action === 'mount' &&
      keys === 'action,image,imageSha384,manifest,trustcache,udid' &&
      [value.image, value.manifest, value.trustcache].every((item) =>
        typeof item === 'string' && item.length > 0 && item.length <= 4096 &&
        !/[\0\r\n]/.test(item))) {
    return value;
  }
  throw new Error('invalid private DDI request');
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
  const imageMounter = await remoteXpc.Services.startMobileImageMounterService(
    request.udid
  );
  try {
    let signatures = await imageMounter.lookup();
    if (!Array.isArray(signatures)) {
      throw new Error('Personalized Developer Disk Image lookup is invalid');
    }
    const expectedImageHash = Buffer.from(request.imageSha384, 'hex');
    if (signatures.length > 0 && !signatures.some((signature) =>
      Buffer.isBuffer(signature) && signature.equals(expectedImageHash))) {
      throw new Error('mounted Personalized Developer Disk Image differs from the pin');
    }
    if (request.action === 'mount') {
      // A successful XCTest run can leave the mounted developer services in a
      // stale state even though the DDI signature still attests correctly.
      // Unmount only after authenticating the existing image, then always
      // mount the validated private snapshot to obtain fresh services.
      if (signatures.length > 0) {
        await imageMounter.unmountImage();
      }
      await imageMounter.mount(request.image, request.manifest, request.trustcache);
      signatures = await imageMounter.lookup();
    }
    if (!Array.isArray(signatures) || signatures.length === 0) {
      throw new Error('Personalized Developer Disk Image is missing');
    }
    if (!signatures.some((signature) =>
      Buffer.isBuffer(signature) && signature.equals(expectedImageHash))) {
      throw new Error('mounted Personalized Developer Disk Image differs from the pin');
    }
    await remoteXpc.resolveTunnelServicePorts(request.udid, SERVICES, {waitMs: 15000});
  } finally {
    await imageMounter.cleanup();
  }
}

main().then(
  () => {},
  () => {
    process.stderr.write('error: private iOS Developer Disk Image check failed\n');
    process.exitCode = 2;
  },
);
