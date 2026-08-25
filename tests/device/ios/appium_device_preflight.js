#!/usr/bin/env node
/*
 * InstallationProxy-only pre-session check. It never installs or launches an app
 * and deliberately emits no device, bundle, signer, or profile metadata.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const MAX_INPUT = 4096;
const OVERTE_ID = 'org.overte.interface.e2e';
const WDA_ID = 'org.overte.WebDriverAgentRunner.xctrunner';

async function readRequest() {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_INPUT) {
      throw new Error('invalid private request');
    }
    chunks.push(chunk);
  }
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!request || Object.keys(request).length !== 1 ||
      typeof request.udid !== 'string' || request.udid.length < 8 ||
      request.udid.length > 128 || /[\0\r\n]/.test(request.udid)) {
    throw new Error('invalid private request');
  }
  return request;
}

async function main() {
  const request = await readRequest();
  const runtime = path.dirname(fs.realpathSync(__filename));
  const modulePath = path.join(
    runtime, 'appium', 'node_modules', 'appium-xcuitest-driver',
    'node_modules', 'appium-ios-device'
  );
  const metadata = JSON.parse(fs.readFileSync(path.join(modulePath, 'package.json'), 'utf8'));
  if (metadata.name !== 'appium-ios-device' || metadata.version !== '3.1.21') {
    throw new Error('immutable device helper dependency mismatch');
  }
  const {services} = require(modulePath);
  const proxy = await services.startInstallationProxyService(request.udid);
  let applications;
  try {
    applications = await proxy.lookupApplications({
      bundleIds: [OVERTE_ID, WDA_ID],
      applicationType: 'User',
      returnAttributes: [
        'CFBundleIdentifier', 'CFBundleExecutable', 'ApplicationType',
        'ProfileValidated', 'SignerIdentity', 'UIFileSharingEnabled',
        'OverteE2ETestBuildContractVersion', 'Entitlements',
        'OverteE2EWebDriverAgentVersion', 'OverteE2EXCUITestDriverVersion',
      ],
    });
  } finally {
    proxy.close();
  }
  if (!applications || Object.keys(applications).length !== 2) {
    throw new Error('required apps are unavailable');
  }
  const overte = applications[OVERTE_ID];
  const wda = applications[WDA_ID];
  const validCommon = (app, expected) => app &&
    app.CFBundleIdentifier === expected &&
    app.ApplicationType === 'User' &&
    app.ProfileValidated === true &&
    typeof app.SignerIdentity === 'string' && app.SignerIdentity.length > 0;
  const signingIdentity = (app, expected) => {
    const entitlements = app && app.Entitlements;
    const team = entitlements && entitlements['com.apple.developer.team-identifier'];
    return typeof team === 'string' && /^[A-Z0-9]{10}$/.test(team) &&
      entitlements['application-identifier'] === `${team}.${expected}` ? team : null;
  };
  const overteTeam = signingIdentity(overte, OVERTE_ID);
  const wdaTeam = signingIdentity(wda, WDA_ID);
  if (!validCommon(overte, OVERTE_ID) || !validCommon(wda, WDA_ID) ||
      overte.SignerIdentity !== wda.SignerIdentity ||
      !overteTeam || overteTeam !== wdaTeam ||
      overte.OverteE2ETestBuildContractVersion !== 1 ||
      overte.UIFileSharingEnabled !== true ||
      wda.OverteE2EWebDriverAgentVersion !== '16.8.0' ||
      wda.OverteE2EXCUITestDriverVersion !== '12.8.0' ||
      typeof wda.CFBundleExecutable !== 'string' ||
      !wda.CFBundleExecutable.endsWith('-Runner')) {
    throw new Error('installed app contract mismatch');
  }
}

main().then(
  () => process.stdout.write('PASS: installed iOS app contracts verified\n'),
  () => {
    process.stderr.write('error: installed iOS app preflight failed\n');
    process.exitCode = 2;
  },
);
