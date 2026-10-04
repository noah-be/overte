import {googleChromeLaunchOptions} from '../google-chrome-selection.mjs';
// SPDX-License-Identifier: Apache-2.0
// Runs against actual domain, assignment servers, gateway Interface, and second native participant.
import { chromium, firefox } from '@playwright/test';
import { launchSystemFirefox } from './system-firefox.mjs';
import { captureNativePeerSnapshot, readNativePeerDiagnostic } from './native-peer-diagnostic.mjs';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { ownedAudioProcess } from './owned-audio-process.mjs';
import { promisify } from 'node:util';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const exec = promisify(execFile);
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const evidenceDirectory = path.join(repo, 'build/browser-lab/evidence');
const duration = Number(process.env.OVERTE_LAB_DURATION_SECONDS || 0);
const browserKind = process.env.OVERTE_LAB_BROWSER || 'chrome';
const isChromium = browserKind === 'chrome' || browserKind === 'chromium' || browserKind === 'system-chromium';
const baseURL = process.env.OVERTE_LAB_URL || 'http://127.0.0.1:8090';
const nativePulse = `unix:${repo}/build/browser-lab/runtime/native-pulse.sock`;
const browserPulse = `unix:${repo}/build/browser-lab/runtime/browser-pulse.sock`;
const evidence = { startedAt: new Date().toISOString(), browser: browserKind, durationSeconds: duration,
    domain: 'hifi://127.0.0.2:45102', nativeVersion: '2026.04.1', syntheticMicrophone: true,
    checkpoints: [], assertions: [], completed: false, endurance: 'Omitted at the user’s explicit instruction; default is a short functional journey.' };
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const save = async () => {
    const contents=JSON.stringify(evidence,null,2)+'\n';
    await writeFile(path.join(evidenceDirectory,`real-session-${browserKind}-${evidence.startedAt.replace(/[:.]/g,'-')}.json`),contents);
    await writeFile(path.join(evidenceDirectory,`real-session-${browserKind}.json`),contents);
};
const checkpoint = async (name, data = {}) => {
    evidence.checkpoints.push({ name, at: new Date().toISOString(), ...data });
    await save(); console.log(JSON.stringify(evidence.checkpoints.at(-1)));
};
async function nativeObservation() {
    const log = await readFile(path.join(repo, 'build/browser-lab/logs/native.log'), 'utf8');
    const observations = log.split('\n').filter(line => line.includes('BROWSER_LAB ') && line.includes('"observation"'));
    assert(observations.length, 'Second actual native client produced observations');
    return JSON.parse(observations.at(-1).split('BROWSER_LAB ')[1]);
}
async function command(value) {
    const sequence = Date.now();
    await writeFile(path.join(repo, 'build/browser-lab/http/command.json'), JSON.stringify({ sequence, ...value }) + '\n');
    await delay(2800);
    return sequence;
}
function rms(buffer) {
    let square = 0, peak = 0;
    for (let i = 0; i + 1 < buffer.length; i += 2) {
        const value = buffer.readInt16LE(i) / 32768; square += value * value; peak = Math.max(peak, Math.abs(value));
    }
    const frames = Math.min(48000, Math.floor(buffer.length / 4));
    const startFrame = Math.floor(buffer.length / 4) - frames;
    const toneAmplitude = frequency => {
        let real=0,imaginary=0;
        for(let i=0;i<frames;i++) {
            const offset=(startFrame+i)*4;
            const value=(buffer.readInt16LE(offset)+buffer.readInt16LE(offset+2))/65536;
            const phase=2*Math.PI*frequency*i/48000;
            real+=value*Math.cos(phase);imaginary+=value*Math.sin(phase);
        }
        return 2*Math.hypot(real,imaginary)/frames;
    };
    return { rms: Math.sqrt(square / (buffer.length / 2)), peak, bytes: buffer.length,
        tone440Amplitude:toneAmplitude(440),tone997Amplitude:toneAmplitude(997) };
}
async function capture(pulseServer, source, filename, seconds = 5) {
    await exec('ffmpeg', ['-hide_banner','-loglevel','error','-y','-f','pulse','-i',source,'-t',String(seconds),'-ar','48000','-ac','2','-f','s16le',filename],
        {env:{...process.env,PULSE_SERVER:pulseServer}, timeout: (seconds + 15) * 1000});
    return rms(await readFile(filename));
}
async function startBrowser() {
    const display = process.env.OVERTE_LAB_BROWSER_DISPLAY;
    const browserEnvironment = {...process.env,PULSE_SERVER:browserPulse,...(display ? {DISPLAY:display} : {})};
    if(browserKind==='chrome')delete browserEnvironment.LD_LIBRARY_PATH;
    if(browserKind==='system-firefox')return launchSystemFirefox({executablePath:process.env.OVERTE_LAB_FIREFOX||'/usr/bin/firefox',
        headless:!display,env:browserEnvironment});
    const options = {...(browserKind==='chrome'?googleChromeLaunchOptions():{}),headless:!display,ignoreDefaultArgs:['--mute-audio'],env:browserEnvironment, args:isChromium
        ? [...(!display ? ['--use-angle=swiftshader'] : []),'--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
            `--use-file-for-fake-audio-capture=${evidenceDirectory}/browser-microphone.wav`]
        : [], firefoxUserPrefs:browserKind==='firefox' ? {'media.navigator.streams.fake':true,'media.navigator.permission.disabled':true} : undefined};
    if(browserKind!=='chrome' && isChromium && process.env.OVERTE_LAB_CHROMIUM)options.executablePath=path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM);
    if(browserKind!=='chrome' && isChromium && process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env.LD_LIBRARY_PATH=path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH);
    return (browserKind === 'firefox' ? firefox : chromium).launch(options);
}
async function screenshot(page, filename) {
    if(!isChromium) {
        await page.screenshot({path:filename,animations:'disabled',caret:'hide'});return;
    }
    // Chromium 153's clipped screenshot path can stall with SwiftShader after pointer lock.
    // Capture the actual viewport surface directly; this does not alter the rendered world.
    const cdp=await page.context().newCDPSession(page);
    let timeout;
    try {
        const capture=await Promise.race([
            cdp.send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false}),
            new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Actual Chromium surface capture exceeded 15 seconds')),15000);})
        ]);
        await writeFile(filename,Buffer.from(capture.data,'base64'));
    } finally {clearTimeout(timeout);await cdp.detach();}
}
let browser;
try {
    await mkdir(evidenceDirectory, {recursive:true});
    evidence.sourceSHA256 = {};
    for (const file of ['browser-client/tests/google-chrome-selection.mjs', 'browser-client/gateway/server.mjs', 'browser-client/gateway/avatar-snapshot-sender.mjs', 'browser-client/gateway/native-bridge.js', 'browser-client/gateway/native-avatar-sample-diagnostics.js', 'browser-client/gateway/native-avatar-stdout-projection.mjs', 'browser-client/lab/manage.py', 'browser-client/gateway/process-lifecycle.mjs', 'browser-client/gateway/validation.mjs', 'browser-client/gateway/permission-policy.mjs', 'browser-client/dist/index.html', 'browser-client/tests/integration/real-session.mjs', 'browser-client/tests/integration/native-peer-diagnostic.mjs', 'browser-client/lab/native-participant.js', 'browser-client/tests/integration/owned-audio-process.mjs', 'browser-client/tests/integration/system-firefox.mjs', 'browser-client/package-lock.json']) {
        evidence.sourceSHA256[file] = createHash('sha256').update(await readFile(path.join(repo, file))).digest('hex');
    }
    for (const file of await readdir(path.join(repo, 'browser-client/dist/assets'))) {
        const relative = `browser-client/dist/assets/${file}`;
        evidence.sourceSHA256[relative] = createHash('sha256').update(await readFile(path.join(repo, relative))).digest('hex');
    }
    browser = await startBrowser(); evidence.browserVersion = browser.version();
    const context = await browser.newContext({viewport:{width:1280,height:800}, permissions:isChromium ? ['microphone'] : []});
    const page = await context.newPage();
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(avatarDeliveryEnabled => {
        const OriginalWebSocket = window.WebSocket;
        window.__labAudio = { incomingNonzero:0, incomingPeak:0, outgoingNonzero:0, outgoingPeak:0, snapshots:[],snapshotTimes:new WeakMap(),states:[] };
        if (avatarDeliveryEnabled) window.__labAudio.delivery = {sockets:0,censored:false,snapshotSockets:new WeakMap(),latestSocket:null};
        window.WebSocket = class extends OriginalWebSocket {
            constructor(...args) {
                super(...args);
                const delivery=window.__labAudio.delivery;
                const ordinal=delivery ? (delivery.sockets<32 ? ++delivery.sockets : (delivery.censored=true,null)) : null;
                if(delivery)delivery.latestSocket=this;
                this.addEventListener('message', event => {
                    if (event.data instanceof ArrayBuffer) {
                        const samples = new Int16Array(event.data); let peak = 0;
                        for (const sample of samples) peak = Math.max(peak,Math.abs(sample)/32768);
                        if (peak > .001) window.__labAudio.incomingNonzero++;
                        window.__labAudio.incomingPeak = Math.max(window.__labAudio.incomingPeak,peak);
                    } else if (typeof event.data === 'string') {
                        try { const message=JSON.parse(event.data); if(message.type==='entities'||message.type==='avatars'){window.__labAudio.snapshotTimes.set(message,performance.now());window.__labAudio.snapshots.push(message);if(delivery)delivery.snapshotSockets.set(message,{ordinal,socket:this});}
                            if(message.type==='state'||message.type==='error'||message.type==='warning')window.__labAudio.states.push({at:Date.now(),...message}); } catch {}
                        if(window.__labAudio.snapshots.length>30)window.__labAudio.snapshots.shift();
                    }
                });
            }
            send(data) {
                if (data instanceof ArrayBuffer) {
                    const samples=new Int16Array(data); let peak=0;
                    for(const sample of samples)peak=Math.max(peak,Math.abs(sample)/32768);
                    if(peak>.001)window.__labAudio.outgoingNonzero++;
                    window.__labAudio.outgoingPeak=Math.max(window.__labAudio.outgoingPeak,peak);
                }
                return super.send(data);
            }
        };
    }, process.env.OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS === '1');
    const join = async () => {
        await page.locator('#domain').fill('overte://127.0.0.2:45102');
        await page.locator('#name').fill(`Browser-Lab-Audit-${browserKind}`);
        await page.locator('#join').click();
        await page.waitForFunction(() => (window.__overte?.connected && window.__overte.entityCount >= 7 && window.__overte.avatarCount >= 1)
            || !!document.querySelector('#notice[data-kind="error"]:not([hidden])'), undefined, {timeout:90000});
        if (!await page.evaluate(() => window.__overte?.connected)) {
            throw Error(await page.locator('#notice').innerText());
        }
        await page.locator('#world canvas').evaluate(canvas => { canvas.tabIndex=0; canvas.focus(); });
    };
    await page.goto(baseURL); await join();
    await checkpoint('actual-domain-joined', await page.evaluate(() => ({ connected:window.__overte.connected,
        entityCount:window.__overte.entityCount,avatarCount:window.__overte.avatarCount,pose:window.__overte.pose })));
    await screenshot(page,path.join(evidenceDirectory,`world-${browserKind}.png`));
    let native = await nativeObservation();
    // Independent native observations are emitted every two seconds. Await a
    // genuine participant update instead of asserting against the pre-join sample.
    for(let attempt=0;attempt<40&&!native.data.avatars.some(avatar=>avatar.displayName===`Browser-Lab-Audit-${browserKind}`);attempt++){
        await delay(250);native=await nativeObservation();
    }
    assert(native.data.entities.some(entity=>entity.modelURL?.startsWith('atp:')), 'Actual domain ATP model exists');
    assert(native.data.entities.some(entity=>entity.modelURL?.startsWith('https:')), 'Actual domain HTTPS model exists');
    assert(native.data.avatars.some(avatar=>avatar.displayName===`Browser-Lab-Audit-${browserKind}`), 'Native client sees browser avatar');
    await checkpoint('native-sees-browser', { nativeSelfId:native.data.selfId, nativeOtherParticipants:native.data.avatars.length });
    const before = await page.evaluate(() => window.__overte.pose.position);
    await page.keyboard.down('KeyW'); await delay(1200); await page.keyboard.up('KeyW'); await delay(3000);
    const after = await page.evaluate(() => window.__overte.pose.position);
    await checkpoint('movement-measured',{before,after,performance:await page.evaluate(()=>window.__overte.performance),
        browserPresentation:await page.evaluate(()=>({visibility:document.visibilityState,focused:document.hasFocus()}))});
    assert(Math.hypot(after.x-before.x, after.z-before.z) > .5, 'Browser WASD moves actual avatar');
    native = await nativeObservation();
    const visibleBrowser = native.data.avatars.find(avatar=>avatar.displayName===`Browser-Lab-Audit-${browserKind}`);
    assert(visibleBrowser && Math.hypot(visibleBrowser.position.x-after.x, visibleBrowser.position.z-after.z) < .2,
        'Actual native position agrees with browser position');
    await checkpoint('browser-movement-synchronized', { before,after,nativePosition:visibleBrowser.position });
    const peerTarget = {x:4,y:1.8,z:2};
    const peerCommandSequence = await command({position:peerTarget});
    const capturedPeer = await page.evaluate(captureNativePeerSnapshot, {fixtureName:'Native-Lab-Participant',target:peerTarget});
    const avatars = capturedPeer.avatars;
    evidence.nativePeerMovementDiagnostic = { browser:capturedPeer.diagnostic,
        native:await readNativePeerDiagnostic(path.join(repo,'build/browser-lab/logs/native.log'), {sequence:peerCommandSequence,target:peerTarget}) };
    await save();
    assert(avatars?.some(avatar=>avatar.displayName==='Native-Lab-Participant' && Math.abs(avatar.position.x-4)<.5),
        'Browser receives second native participant movement');
    await checkpoint('native-movement-synchronized');
    await page.keyboard.down('KeyW'); await delay(1000); await page.keyboard.up('KeyW'); await delay(1000);
    const collisionPose=await page.evaluate(()=>window.__overte.pose.position);
    assert(collisionPose.z > -2.4,'Actual domain interactable geometry blocks browser movement');
    await checkpoint('actual-world-collision',{position:collisionPose});
    native=await nativeObservation();
    const interactBefore=native.data.entities.find(entity=>entity.name==='Browser Lab Interactable');
    await screenshot(page,path.join(evidenceDirectory,`interaction-${browserKind}.png`));
    await page.keyboard.press('KeyE');
    let interactAfter;
    for(let attempt=0;attempt<40;attempt++) {
        await delay(250); native=await nativeObservation();
        interactAfter=native.data.entities.find(entity=>entity.name==='Browser Lab Interactable');
        if(JSON.stringify(interactAfter.color)!==JSON.stringify(interactBefore.color))break;
    }
    await checkpoint('interaction-measured',{before:interactBefore.color,after:interactAfter.color,
        pose:await page.evaluate(()=>window.__overte.pose),connected:await page.evaluate(()=>window.__overte.connected),
        states:await page.evaluate(()=>window.__labAudio.states),events:await page.locator('#events').textContent()});
    assert.notDeepEqual(interactAfter.color,interactBefore.color,'Browser interaction changes real domain object observed by native');
    await checkpoint('interaction-observed-by-native',{before:interactBefore.color,after:interactAfter.color});
    {
        await page.locator('#microphone').click();
        await page.waitForFunction(()=>window.__labAudio.outgoingNonzero>10,undefined,{timeout:15000});
        const nativeReceived=await capture(nativePulse,'lab_output.monitor',path.join(evidenceDirectory,`browser-to-native-${browserKind}.pcm`));
        assert(nativeReceived.rms>.001,'Native actual audio output contains browser synthetic microphone signal');
        if(isChromium)assert(nativeReceived.tone440Amplitude>.001,'Native output contains the actual known 440Hz browser microphone tone');
        await page.locator('#microphone').click();
        await checkpoint('browser-to-native-audio',{input:isChromium ? 'Synthetic 440Hz fake microphone WAV' : 'Firefox generated fake microphone signal',nativeOutput:nativeReceived,
            browser:await page.evaluate(()=>({ incomingNonzero:window.__labAudio.incomingNonzero,incomingPeak:window.__labAudio.incomingPeak,
                outgoingNonzero:window.__labAudio.outgoingNonzero,outgoingPeak:window.__labAudio.outgoingPeak }))});
        await command({muted:false});
        const incomingBefore=await page.evaluate(()=>window.__labAudio.incomingNonzero);
        const inject=ownedAudioProcess('ffmpeg',['-hide_banner','-loglevel','error','-re','-f','lavfi','-i','sine=frequency=997:sample_rate=48000','-t','9','-ac','1','-f','pulse','-device','lab_input','Native synthetic microphone'],{env:{...process.env,PULSE_SERVER:nativePulse},timeoutMs:12000,graceMs:1000});
        let browserReceived;
        try {
            await delay(1000);
            browserReceived=await capture(browserPulse,'browser_output.monitor',path.join(evidenceDirectory,`native-to-browser-${browserKind}.pcm`));
            const completed=await inject.completion;
            assert.equal(completed.kind,'exited','The owned native tone injector finishes within its deadline');
            assert.equal(completed.exitCode,0,'The native tone injector succeeds');
        } finally {
            try { await inject.stop(); } finally { await command({muted:true}); }
        }
        assert(await page.evaluate(()=>window.__labAudio.incomingNonzero)>incomingBefore+10,'Browser receives nonzero actual native mixed audio PCM');
        assert(browserReceived.rms>.001,'Browser actual playback audio output contains native synthetic microphone signal');
        assert(browserReceived.tone997Amplitude>.001,'Browser playback contains the actual known 997Hz native microphone tone');
        await checkpoint('native-to-browser-audio',{input:'Synthetic 997Hz injected private native microphone',browserOutput:browserReceived});
    }
    const firstSessionStates = await page.evaluate(() => window.__labAudio.states);
    const connections = firstSessionStates.filter(state => state.state === 'connected');
    assert.equal(connections.length, 1, 'Native session remains connected without unexpected reconnects throughout the actual journey');
    await checkpoint('stable-real-connection', { connectedAt:connections[0].at, connectedSeconds:(Date.now()-connections[0].at)/1000 });
    const departedUUID=await page.evaluate(()=>window.__labAudio.snapshots.filter(snapshot=>snapshot.type==='avatars').at(-1)?.selfId);
    await page.keyboard.press('Escape'); await page.locator('#leave').click();
    let departureObserved=false;
    for(let attempt=0;attempt<32;attempt++) {
        native=await nativeObservation();
        if(!native.data.avatars.some(avatar=>String(avatar.id)===String(departedUUID))){departureObserved=true;break;}
        await delay(250);
    }
    assert(departureObserved,'Clean leave removes the departed browser avatar from the actual native participant');
    await checkpoint('native-observed-clean-leave',{departedUUID});
    assert.equal(await page.evaluate(()=>window.__overte.connected),false,'Leaving resets native and browser session');
    await join(); await delay(1500);
    const rejoinPose=await page.evaluate(()=>window.__overte.pose);
    await checkpoint('reconnected-to-actual-domain',{pose:rejoinPose});
    assert(rejoinPose.position.y > .3 && rejoinPose.position.y < 2,'Reconnected browser is above the real lab floor');
    const rejoinBefore=rejoinPose.position;
    await page.keyboard.down('KeyD'); await delay(700); await page.keyboard.up('KeyD'); await delay(500);
    const rejoinAfter=await page.evaluate(()=>window.__overte.pose.position);
    await checkpoint('reconnection-movement-observed',{before:rejoinBefore,after:rejoinAfter,
        controls:await page.evaluate(()=>({tabletVisible:window.__overte.tabletVisible,focusedTag:document.activeElement?.tagName,
            focusedLabel:document.activeElement?.getAttribute('aria-label'),connected:window.__overte.connected,
            performance:window.__overte.performance})),nativePosition:(await nativeObservation()).data.position});
    assert(Math.hypot(rejoinAfter.x-rejoinBefore.x,rejoinAfter.z-rejoinBefore.z)>.4,'Reconnected browser can move through the actual world');
    await checkpoint('reconnection-movement',{before:rejoinBefore,after:rejoinAfter});
    const lookBefore=await page.evaluate(()=>window.__overte.pose.orientation);
    await page.locator('#world canvas').click();
    await page.mouse.move(800,400); await delay(250);
    const lookAfter=await page.evaluate(()=>window.__overte.pose.orientation);
    assert.notDeepEqual(lookAfter,lookBefore,'Actual browser mouse controls view orientation');
    await checkpoint('mouse-look',{before:lookBefore,after:lookAfter});
    await page.keyboard.press('KeyV');
    await checkpoint('final-view',{pose:await page.evaluate(()=>window.__overte.pose),
        avatarSnapshot:await page.evaluate(()=>window.__labAudio.snapshots.filter(snapshot=>snapshot.type==='avatars').at(-1))});
    await page.keyboard.press('Escape');
    await screenshot(page,path.join(evidenceDirectory,`world-final-${browserKind}.png`));
    await command({camera:{position:{x:6,y:4,z:5},target:{x:0,y:1,z:0}}});
    await exec('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','x11grab','-video_size','1024x768','-i',':95','-frames:v','1',
        path.join(evidenceDirectory,`native-final-${browserKind}.png`)],{timeout:15000});
    const start=Date.now();
    for(let iteration=0;Date.now()-start<duration*1000;iteration++) {
        await delay(Math.min(30000,duration*1000-(Date.now()-start)));
        const metrics=await page.evaluate(()=>({connected:window.__overte.connected,entities:window.__overte.entityCount,
            participants:window.__overte.avatarCount,pose:window.__overte.pose,audio:window.__overte.audio}));
        assert(metrics.connected && metrics.entities>=7 && metrics.participants>=1,'Actual browser and native remain in same world');
        native=await nativeObservation();
        assert(Date.now()-native.at<10000,'Actual native observation is recent');
        assert(native.data.avatars.some(avatar=>avatar.displayName===`Browser-Lab-Audit-${browserKind}`),'Native continuously sees browser');
        await checkpoint('soak-checkpoint',{elapsedSeconds:(Date.now()-start)/1000,metrics,nativeSelfId:native.data.selfId});
    }
    assert.deepEqual(errors,[],'Browser emitted no uncaught application errors');
    evidence.completed=true; evidence.finishedAt=new Date().toISOString();
    evidence.continuousSharedSessionSeconds=(Date.now()-start)/1000;
    evidence.journeySeconds=(Date.now()-Date.parse(evidence.startedAt))/1000;
    await checkpoint('all-real-session-assertions-passed');
} catch(error) {
    evidence.error={message:error.message,stack:error.stack};await save();console.error(error);process.exitCode=1;
} finally { await browser?.close(); }
