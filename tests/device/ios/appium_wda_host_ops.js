/*
 * Fedora overlay for Appium XCUITest 12.8.0 WebDriverAgent host operations.
 *
 * iOS 26 requires the current reverse XCTestDriverInterface handshake.  The
 * pinned appium-ios-remotexpc 5.15.3 process launcher predates that handshake,
 * while pinned PyMobileDevice3 11.1.5 implements it.  This overlay is copied
 * only into the immutable Fedora runtime; Darwin keeps Appium's native path.
 */

import {spawn} from 'node:child_process';
import {supportsApiLevel18, supportsApiLevel27} from '../utils/index.js';

const PYTHON = '/usr/bin/python3.14';
const WDA_PORT = 8100;
const MAX_TOOL_OUTPUT = 64 * 1024;
const KEEPER_GRACEFUL_STOP_MS = 12000;
const KEEPER_FORCE_REAP_MS = 3000;
const KEEPER_FAILURE_PHASES = new Set([
    'host-platform', 'keeper-reap', 'parent-death-signal', 'parent-lost', 'request',
    'request-endpoint', 'request-environment', 'runtime-version',
    'rsd-connect', 'rsd-identity', 'xctest-config', 'xctest-start',
    'wda-ready', 'wda-ready-runner-disconnected', 'wda-ready-runner-error',
    'wda-ready-runner-returned', 'wda-ready-runner-runtime',
    'wda-ready-runner-timeout', 'wda-ready-timeout', 'session-lifetime',
    'session-lifetime-runner-disconnected', 'session-lifetime-runner-error',
    'session-lifetime-runner-returned', 'session-lifetime-runner-runtime',
    'session-lifetime-runner-timeout', 'unexpected',
]);
const XCODE_ONLY_CAPS = [
    'usePrebuiltWDA',
    'useXctestrunFile',
    'prebuildWDA',
    'xcodeOrgId',
    'xcodeSigningId',
    'xcodeConfigFile',
    'keychainPath',
    'keychainPassword',
    'allowProvisioningDeviceRegistration',
    'resultBundlePath',
];
const activeXctestKeepers = new Map();

export function isStrictHostUtilityMode(opts, platform = process.platform) {
    return platform !== 'darwin' && Boolean(opts.webDriverAgentUrl || opts.usePreinstalledWDA);
}

export function assertWdaHostSessionCapsSupported(opts, platform = process.platform) {
    if (platform === 'darwin') {
        return;
    }
    if (!opts.webDriverAgentUrl && !opts.usePreinstalledWDA) {
        throw new Error(`The selected XCUITest session strategy requires macOS with Xcode. ` +
            `Use 'appium:usePreinstalledWDA' with a signed prebuilt WebDriverAgent or provide ` +
            `'appium:webDriverAgentUrl' to run from '${platform}'.`);
    }
    if (!opts.udid || opts.udid.toLowerCase() === 'auto') {
        throw new Error(`Running XCUITest from '${platform}' without macOS/Xcode requires an explicit real-device ` +
            `'appium:udid'. Simulator discovery and automatic device selection require macOS.`);
    }
    if (opts.usePreinstalledWDA && !opts.webDriverAgentUrl && !opts.platformVersion) {
        throw new Error(`Running preinstalled WebDriverAgent from '${platform}' requires 'appium:platformVersion' ` +
            `so RemoteXPC eligibility can be checked without probing host Xcode or Simulator tools.`);
    }
    const xcodeOnlyCaps = XCODE_ONLY_CAPS.filter((capName) => Boolean(opts[capName]));
    if (opts.usePreinstalledWDA && !opts.webDriverAgentUrl && xcodeOnlyCaps.length > 0) {
        throw new Error(`The following capabilities require macOS/Xcode and cannot be used with the ` +
            `RemoteXPC preinstalled WebDriverAgent strategy on '${platform}': ` +
            xcodeOnlyCaps.join(', '));
    }
}

export function createWdaHostOps(driver) {
    return {
        simulator: createSimulatorHostOps(driver),
        realDevicePreinstalled: createRealDevicePreinstalledHostOps(driver),
    };
}

export function assertWdaHostPlatformSupported(driver) {
    if (process.platform === 'darwin') {
        return;
    }
    assertWdaHostSessionCapsSupported(driver.opts);
    if (driver.opts.webDriverAgentUrl) {
        return;
    }
    if (!driver.isRealDevice()) {
        throw new Error(`XCUITest simulator sessions require macOS with Xcode. ` +
            `Use a real device with 'appium:usePreinstalledWDA' or provide 'appium:webDriverAgentUrl' ` +
            `to run from '${process.platform}'.`);
    }
    if (!driver.opts.usePreinstalledWDA) {
        throw new Error(`The default real-device WebDriverAgent startup strategy requires macOS with Xcode. ` +
            `Use 'appium:usePreinstalledWDA' with a signed prebuilt WebDriverAgent or provide ` +
            `'appium:webDriverAgentUrl' to run from '${process.platform}'.`);
    }
    if (driver.opts.platformVersion && !supportsApiLevel18(driver.opts.platformVersion, driver.opts.platformName)) {
        throw new Error(`Running preinstalled WebDriverAgent from '${process.platform}' requires a real device ` +
            `with RemoteXPC tunnel support. The current platformVersion is ` +
            `'${driver.opts.platformVersion}'; use iOS/tvOS 18.0 or newer, or provide ` +
            `'appium:webDriverAgentUrl' for an externally managed WDA.`);
    }
    if (!driver.remoteXPCFacade.eligible) {
        throw new Error(`RemoteXPC is required to launch preinstalled WebDriverAgent from '${process.platform}', ` +
            `but this session is not eligible for RemoteXPC.`);
    }
}

function stringifyLaunchEnvironment(env) {
    return Object.entries(env).reduce((acc, [key, value]) => {
        acc[key] = String(value);
        return acc;
    }, {});
}

function createSimulatorHostOps(driver) {
    return {
        async launchPreinstalled({udid, bundleId, env}) {
            await driver.device.simctl.exec('launch', {
                args: ['--terminate-running-process', udid, bundleId],
                env,
            });
        },
        async terminate({bundleId}) {
            await driver.device.terminateApp(bundleId);
        },
    };
}

async function terminateExactRunner(driver, udid, bundleId) {
    const dvt = await driver.remoteXPCFacade.requireService(
        'terminate preinstalled WebDriverAgent',
        (Services) => Services.startDVTService(udid),
    );
    try {
        const pid = await dvt.processControl.getPidForBundleIdentifier(bundleId);
        if (pid) {
            await dvt.processControl.kill(pid);
        }
    } finally {
        await dvt.dvtService.close();
    }
}

function keeperKey(udid, bundleId) {
    return `${udid}\0${bundleId}`;
}

async function stopXctestKeeper(child) {
    if (!child || child.exitCode !== null || child.signalCode !== null) {
        return;
    }
    const exited = new Promise((resolve) => child.once('exit', resolve));
    child.kill('SIGTERM');
    let timer;
    const graceful = await Promise.race([
        exited.then(() => true),
        new Promise((resolve) => {
            timer = setTimeout(() => resolve(false), KEEPER_GRACEFUL_STOP_MS);
        }),
    ]);
    clearTimeout(timer);
    if (!graceful && child.exitCode === null && child.signalCode === null) {
        child.kill('SIGKILL');
        const killed = await Promise.race([
            exited.then(() => true),
            new Promise((resolve) => {
                timer = setTimeout(() => resolve(false), KEEPER_FORCE_REAP_MS);
            }),
        ]);
        clearTimeout(timer);
        if (!killed && child.exitCode === null && child.signalCode === null) {
            throw new Error('XCTest keeper could not be reaped');
        }
    }
}

async function waitForKeeperReady(child, timeoutMs) {
    await new Promise((resolve, reject) => {
        let output = Buffer.alloc(0);
        const timer = setTimeout(
            () => finish(new Error('XCTest keeper readiness timed out')),
            timeoutMs,
        );
        const finish = (error) => {
            clearTimeout(timer);
            child.stdout?.off('data', onData);
            child.off('error', onError);
            child.off('exit', onExit);
            error ? reject(error) : resolve();
        };
        const onData = (chunk) => {
            output = Buffer.concat([output, chunk]);
            if (output.length > 6 || !Buffer.from('READY\n').subarray(0, output.length).equals(output)) {
                finish(new Error('XCTest keeper returned invalid readiness data'));
            } else if (output.length === 6) {
                finish();
            }
        };
        const onError = () => finish(new Error('XCTest keeper could not start'));
        const onExit = () => finish(new Error('XCTest keeper exited before readiness'));
        child.stdout?.on('data', onData);
        child.once('error', onError);
        child.once('exit', onExit);
    });
}

function captureKeeperFailure(child) {
    let output = Buffer.alloc(0);
    let invalid = false;
    let finish;
    const complete = new Promise((resolve) => { finish = resolve; });
    if (!child.stderr) {
        invalid = true;
        finish();
    } else {
        child.stderr.on('data', (chunk) => {
            if (!Buffer.isBuffer(chunk) || output.length + chunk.length > MAX_TOOL_OUTPUT) {
                invalid = true;
                output = Buffer.alloc(0);
                return;
            }
            output = Buffer.concat([output, chunk]);
        });
        child.stderr.once('end', finish);
        child.stderr.once('close', finish);
        child.stderr.once('error', () => {
            invalid = true;
            finish();
        });
    }
    return async () => {
        await Promise.race([
            complete,
            new Promise((resolve) => setTimeout(resolve, 250)),
        ]);
        if (invalid) {
            return null;
        }
        const match = output.toString('ascii').match(
            /^error: immutable Fedora XCTest keeper failed phase=([a-z-]+)\n$/,
        );
        return match && KEEPER_FAILURE_PHASES.has(match[1]) ? match[1] : null;
    };
}

function validatePymobiledevice3Environment(bundleId, env, wdaRemotePort) {
    const launchEnvironment = stringifyLaunchEnvironment(env);
    const keys = Object.keys(launchEnvironment).sort();
    if (wdaRemotePort !== WDA_PORT ||
        keys.join(',') !== 'USE_PORT,WDA_PRODUCT_BUNDLE_IDENTIFIER' ||
        launchEnvironment.USE_PORT !== String(WDA_PORT) ||
        launchEnvironment.WDA_PRODUCT_BUNDLE_IDENTIFIER !== bundleId) {
        throw new Error('The immutable Fedora XCTest launcher supports only the fixed WDA port and default environment');
    }
}

async function launchWithPymobiledevice3(driver, options) {
    const {udid, bundleId, env, wdaRemotePort, timeoutMs} = options;
    validatePymobiledevice3Environment(bundleId, env, wdaRemotePort);
    const sitePackages = process.env.OVERTE_PYMOBILEDEVICE3_SITE_PACKAGES;
    const helper = process.env.OVERTE_PYMOBILEDEVICE3_XCTEST_HELPER;
    const privateHome = process.env.APPIUM_HOME;
    if (!sitePackages || !sitePackages.startsWith('/') ||
        sitePackages.includes('\0') || sitePackages.includes('\n') ||
        sitePackages.includes('/../') || sitePackages.endsWith('/..') ||
        !helper || !helper.startsWith('/') || helper.includes('\0') ||
        helper.includes('\n') || helper.includes('/../') || helper.endsWith('/..') ||
        !privateHome || !privateHome.startsWith('/') || privateHome.includes('\0') ||
        privateHome.includes('\n') || privateHome.includes('/../') ||
        privateHome.endsWith('/..')) {
        throw new Error('The immutable PyMobileDevice3 runtime is unavailable');
    }
    const remoteXpc = await driver.remoteXPCFacade.requireModule();
    const endpoint = await remoteXpc.getTunnelForDevice(udid, {waitMs: 15000});
    if (!endpoint || endpoint.udid !== udid || typeof endpoint.host !== 'string' ||
        !Number.isInteger(endpoint.port) || endpoint.port < 1 || endpoint.port > 65535) {
        throw new Error('The RemoteXPC endpoint does not match the selected physical device');
    }

    const key = keeperKey(udid, bundleId);
    const previous = activeXctestKeepers.get(key);
    if (previous) {
        await stopXctestKeeper(previous);
        activeXctestKeepers.delete(key);
        // Only terminate a runner that this Appium process previously owned.
        // A fresh Fedora session follows an attested DDI remount; killing an
        // unrelated/stale process here races the new XCTest service bootstrap.
        await terminateExactRunner(driver, udid, bundleId);
    }
    const boundedTimeout = Math.max(1000, Math.min(Number(timeoutMs) || 30000, 35000));
    const pythonEnvironment = {
        HOME: privateHome,
        LANG: 'C.UTF-8',
        LC_ALL: 'C.UTF-8',
        PATH: '/usr/bin',
        PYTHONNOUSERSITE: '1',
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONPATH: sitePackages,
    };
    let child;
    let keeperFailurePhase = async () => null;
    try {
        child = spawn(PYTHON, ['-S', '-P', '-B', helper], {
            cwd: '/', env: pythonEnvironment,
            stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
        });
        keeperFailurePhase = captureKeeperFailure(child);
        const request = JSON.stringify({
            schemaVersion: 1,
            udid,
            rsdHost: endpoint.host,
            rsdPort: endpoint.port,
            wdaBundleId: bundleId,
            wdaPort: WDA_PORT,
            environment: stringifyLaunchEnvironment(env),
        }) + '\n';
        if (Buffer.byteLength(request) > MAX_TOOL_OUTPUT || !child.stdin) {
            throw new Error('The private XCTest keeper request is invalid');
        }
        child.stdin.write(request);
        await waitForKeeperReady(child, boundedTimeout);
        activeXctestKeepers.set(key, child);
        child.once('exit', () => {
            if (activeXctestKeepers.get(key) === child) {
                activeXctestKeepers.delete(key);
            }
        });
    } catch (error) {
        let keeperCleanupFailed = false;
        try {
            await stopXctestKeeper(child);
        } catch {
            keeperCleanupFailed = true;
        }
        const phase = await keeperFailurePhase();
        try {
            await terminateExactRunner(driver, udid, bundleId);
        } catch {}
        const diagnosticPhase = phase || (keeperCleanupFailed ? 'keeper-reap' : null);
        const diagnostic = diagnosticPhase ? ` (phase: ${diagnosticPhase})` : '';
        throw new Error(`The immutable Fedora XCTest launcher could not start WebDriverAgent${diagnostic}`);
    }
}

function createRealDevicePreinstalledHostOps(driver) {
    return {
        async launchPreinstalled(options) {
            if (process.platform !== 'darwin') {
                await launchWithPymobiledevice3(driver, options);
                return;
            }
            const {udid, bundleId, env} = options;
            try {
                const dvt = await driver.remoteXPCFacade.requireService(
                    'launch preinstalled WebDriverAgent',
                    (Services) => Services.startDVTService(udid),
                );
                try {
                    await dvt.processControl.launch({
                        bundleId,
                        environment: stringifyLaunchEnvironment(env),
                        killExisting: true,
                    });
                } finally {
                    await dvt.dvtService.close();
                }
            } catch (err) {
                if (supportsApiLevel27(driver.opts.platformVersion)) {
                    throw new Error(`Failed to launch the preinstalled WebDriverAgent via RemoteXPC: ${err.message}`, {cause: err});
                }
                driver.log.warn(`Failed to launch preinstalled WebDriverAgent via RemoteXPC. ` +
                    `Falling back to devicectl. Original error: ${err.message}`);
                const {devicectl} = driver.device;
                if (!devicectl) {
                    throw err;
                }
                await devicectl.launchApp(bundleId, {env, terminateExisting: true});
            }
        },
        async terminate({udid, bundleId}) {
            try {
                const key = keeperKey(udid, bundleId);
                let cleanupError;
                try {
                    await stopXctestKeeper(activeXctestKeepers.get(key));
                } catch (error) {
                    cleanupError = error;
                }
                activeXctestKeepers.delete(key);
                try {
                    await terminateExactRunner(driver, udid, bundleId);
                } catch (error) {
                    cleanupError ||= error;
                }
                if (cleanupError) {
                    throw cleanupError;
                }
            } catch (err) {
                if (process.platform !== 'darwin') {
                    throw err;
                }
                driver.log.warn(`Failed to terminate preinstalled WebDriverAgent via RemoteXPC. ` +
                    `Falling back to devicectl. Original error: ${err.message}`);
                const {devicectl} = driver.device;
                if (!devicectl) {
                    throw err;
                }
                await devicectl.terminateApp(bundleId);
            }
        },
    };
}
