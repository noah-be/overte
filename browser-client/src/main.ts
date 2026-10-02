// SPDX-License-Identifier: Apache-2.0
import './style.css';
import { BrowserAudio } from './audio';
import { CompressedColorSession } from './compressed-color-session';
import type { ServerMessage } from './session';
import { BrowserWorld } from './world';
import { BrowserTablet } from './tablet';
import { NavigationHistory, type NavigationAttempt } from './navigation-history';
import { VisitorPreferenceStore } from './visitor-preferences';
import { VisitorPersonaStore } from './visitor-persona';
import { BrowserGraphicsController } from './browser-graphics-controller';
import {validateBrowserGraphics} from '../shared/browser-graphics.mjs';

const element = <T extends HTMLElement>(id:string) => document.getElementById(id) as T;
const form = element<HTMLFormElement>('join-form');
const domainInput = element<HTMLInputElement>('domain');
const nameInput = element<HTMLInputElement>('name');
const joinButton = element<HTMLButtonElement>('join');
const places = element<HTMLSelectElement>('places');
const micButton = element<HTMLButtonElement>('microphone');
const soundButton = element<HTMLButtonElement>('sound');
const tabletButton = element<HTMLButtonElement>('tablet');
const notice = element('notice');
let world: BrowserWorld | undefined;
let audio: BrowserAudio | undefined;
let tablet: BrowserTablet | undefined;
let graphics: BrowserGraphicsController | undefined;
let epoch = 0;
let entityCount = 0;
let avatarCount = 0;
let joining = false;
let ready = false;
let worldLoaded = false;
let errorNotice = false;
let microphonePending = false;
const navigationHistory = new NavigationHistory();
let navigationAttempt:NavigationAttempt | undefined;
let permissionRevision = 0;
const navigationNonces = new Set<string>();
// Access itself can be refused by browser privacy/storage settings.
let visitorStorage:Pick<Storage,'getItem'|'setItem'>;
try { visitorStorage = window.localStorage; }
catch { visitorStorage = {getItem:()=>{throw Error('Storage unavailable');},setItem:()=>{throw Error('Storage unavailable');}}; }
const visitorPreferences = new VisitorPreferenceStore(visitorStorage,message=>log(message,'warning'));
const visitorPersona = new VisitorPersonaStore(visitorStorage,message=>log(message,'warning'));
if (visitorPersona.snapshot().displayName!==undefined) nameInput.value=visitorPersona.snapshot().displayName!;

function sendNavigationHistory():void {
    if (ready && permissionRevision > 0) session.send({type:'navigationHistoryState', permissionRevision, ...navigationHistory.state});
}

function log(message:string, kind='info'): void {
    const item = document.createElement('li');
    item.textContent = `${new Date().toLocaleTimeString()} · ${message}`;
    element('events').prepend(item);
    while (element('events').children.length > 30) element('events').lastElementChild?.remove();
    if (kind === 'error' || kind === 'warning') {
        notice.textContent = message;
        notice.dataset.kind = kind;
        notice.hidden = false;
        errorNotice = kind === 'error';
    }
}
function showState(state:string): void {
    const connection = element('connection');
    connection.dataset.state = state;
    connection.replaceChildren(document.createElement('i'), document.createTextNode(` ${state[0].toUpperCase()}${state.slice(1)}`));
}
function updateStats(): void {
    element('stats').textContent = `${entityCount} entities · ${avatarCount} other participants`;
}
function updateMicrophone(): void {
    micButton.textContent = audio?.muted === false ? 'Mute microphone' : 'Enable microphone';
    micButton.setAttribute('aria-pressed', String(audio?.muted === false));
    micButton.disabled = microphonePending;
}

function reset(): void {
    if (ready && world) navigationHistory.rememberDeparture(world.getPose());
    epoch++;
    graphics?.close();graphics=undefined;
    session.leave();
    tablet?.dispose(); tablet = undefined; tabletButton.disabled = true;
    world?.dispose();
    world = undefined;
    void audio?.dispose();
    audio = undefined;
    joining = false;
    ready = false;
    worldLoaded = false;
    microphonePending = false;
    navigationAttempt = undefined;
    navigationHistory.cancel();
    permissionRevision = 0;
    navigationNonces.clear();
    entityCount = avatarCount = 0;
    joinButton.disabled = false;
    element('welcome').hidden = false;
    element('session-panel').hidden = true;
    element('help').hidden = true;
    element('aim').hidden = true;
    element('loading').hidden = true;
    showState('disconnected');
    updateMicrophone();
}
function onMessage(message:ServerMessage): void {
    switch (message.type) {
        case 'state':
            if (message.state === 'error') {
                const detail = message.message || 'Unable to join this domain.';
                reset(); log(detail, 'error'); break;
            }
            if (message.state === 'disconnected') {
                reset(); log(message.message || 'You left the domain.'); break;
            }
            showState(message.state);
            if (message.message) log(message.message);
            if (message.state === 'connecting' && ready) {
                ready = false;
                world?.invalidateSourceTexts();
                world?.invalidateModelParses();
                graphics?.setAuthority(permissionRevision,false);
                worldLoaded = false;
                world?.setEnabled(false);
                tablet?.setConnected(false); tabletButton.disabled = true;
                element('aim').hidden = true;
                world?.setEntities([]);
                world?.setAvatars([]);
                entityCount = avatarCount = 0;
                updateStats();
                audio?.stopMicrophone();
                updateMicrophone();
                element('loading').hidden = false;
                element('loading-text').textContent = 'Reconnecting to domain…';
            }
            if (message.state === 'connected' && !ready) {
                ready = true;
                if (navigationAttempt) navigationHistory.commit(navigationAttempt);
                navigationAttempt = undefined;
                if (message.permissionRevision) permissionRevision = message.permissionRevision;
                graphics?.setAuthority(permissionRevision,true);
                sendNavigationHistory();
                tablet?.setConnected(true); tabletButton.disabled = false;
                joining = false;
                world?.setEnabled(worldLoaded);
                element('aim').hidden = !worldLoaded;
                element('welcome').hidden = true;
                element('session-panel').hidden = false;
                element('help').hidden = false;
                element('loading-text').textContent = 'Loading world entities and assets…';
                if (entityCount) element('loading').hidden = true;
                session.send({type:'mute', muted:true});
            }
            break;
        case 'entities':
        case 'entityUpdates':
            if (message.type === 'entities') world?.setEntities(message.entities);
            else { world?.removeEntities(message.removed); world?.upsertEntities(message.entities); }
            entityCount = world?.entityCount ?? 0;
            if (entityCount || worldLoaded) {
                worldLoaded = true;
                world?.setEnabled(ready);
                element('aim').hidden = !ready;
                element('loading').hidden = true;
            } else {
                element('loading-text').textContent = 'Waiting for visible world entities…';
            }
            updateStats();
            break;
        case 'avatars':
            if (message.selfId) world?.setLocalAvatar(message.selfId);
            world?.setAvatars(message.avatars);
            avatarCount = message.avatars.filter(avatar => avatar.id !== message.selfId).length;
            updateStats();
            break;
        case 'pose':
            world?.setSpawn(message.position, message.orientation);
            break;
        case 'poseRequest':
            if (!world || !ready || (permissionRevision && message.permissionRevision !== permissionRevision)) break;
            world.setSpawn(message.position, message.orientation);
            session.send({type:'poseAccepted', nonce:message.nonce, permissionRevision:message.permissionRevision});
            break;
        case 'navigation':
        case 'navigationHistory': {
            if (!ready || navigationNonces.has(message.nonce) || (permissionRevision && message.permissionRevision !== permissionRevision)) break;
            if (navigationNonces.size >= 64) navigationNonces.delete(navigationNonces.values().next().value!);
            navigationNonces.add(message.nonce);
            const target = message.type === 'navigation' ? {domain:message.domain} : navigationHistory.traverse(message.direction);
            if (!target) { sendNavigationHistory(); log('No previous world is available in this direction.', 'warning'); break; }
            const domain = target.domain;
            // Revoke and dispose the entire old worker, world, microphone and
            // Tablet before the ordinary gateway admission for the new world.
            const direction = message.type === 'navigationHistory' ? message.direction : undefined;
            void joinDomain(domain, direction);
            break;
        }
        case 'visitorPreferences':
            if (ready && message.permissionRevision === permissionRevision) visitorPreferences.update({bookmarks:message.bookmarks,...(message.home === undefined ? {} : {home:message.home})});
            break;
        case 'visitorPersona':
            if (ready && message.permissionRevision===permissionRevision) {
                const fields=Object.fromEntries(['displayName','avatarURL','avatarScale','avatarFavorites']
                    .filter(key=>Object.hasOwn(message,key)).map(key=>[key,message[key as keyof typeof message]]));
                visitorPersona.update(fields);
                if (message.displayName!==undefined) nameInput.value=message.displayName;
            }
            break;
        case 'error': log(message.message, 'error'); break;
        case 'warning': log(message.message, 'warning'); break;
        case 'interaction': log(message.message); break;
        case 'tablet':
            if (!ready || message.revision < permissionRevision) break;
            if (message.revision !== permissionRevision) { permissionRevision = message.revision; graphics?.setAuthority(permissionRevision,true); sendNavigationHistory(); }
            tablet?.receive(message); break;
    }
}
const session = new CompressedColorSession({
    message: onMessage,
    audio: data => audio?.receive(data),
    closed: reason => { reset(); if (!errorNotice) log(reason, 'warning'); },
    error: reason => log(reason, 'error'),
});

async function joinDomain(domain:string, direction?:'back'|'forward'):Promise<void> {
    if (joining) return;
    reset();
    navigationAttempt = direction ? navigationHistory.traverse(direction) : navigationHistory.begin(domain);
    if (!navigationAttempt) return;
    domainInput.value = domain;
    const generation = epoch;
    joining = true;
    errorNotice = false;
    notice.hidden = true;
    joinButton.disabled = true;
    element('welcome').hidden = true;
    element('loading').hidden = false;
    element('loading-text').textContent = 'Connecting to domain…';
    element('session-panel').hidden = false;
    element('domain-name').textContent = domainInput.value.trim();
    element('stats').textContent = 'Starting an isolated session…';
    showState('connecting');
    try {
        world = new BrowserWorld(element('world'), {
            resolveAsset: url => session.assetURL(url),
            gpuTiming: new URLSearchParams(location.search).get('gpuTiming') === '1',
            cpuFrameTiming: new URLSearchParams(location.search).get('cpuFrameTiming') === '1',
            renderCpuTiming: new URLSearchParams(location.search).get('renderCpuTiming') === '1',
            staticModelMatrices: new URLSearchParams(location.search).get('staticModelMatrices') === '1',
            shaderWarmup: new URLSearchParams(location.search).get('shaderWarmup') === '1',
            texturePreparation: new URLSearchParams(location.search).get('texturePreparation') === '1',
            bitmapUpload: new URLSearchParams(location.search).get('bitmapUpload') === '1',
            modelParseTurn: new URLSearchParams(location.search).get('modelParseTurn') === '1',
            compressedColors: (capabilities, signal) => session.compressedColors(capabilities, signal),
            captureAssetAuthority: () => session.captureAssetAuthority(),
            onPose: pose => session.sendPose(pose),
            onInteract: entity => session.send({type:'interact', entityId:entity.id}),
            onStatus: log,
        });
        const graphicsWorld=world;
        try {
            const saved=visitorStorage.getItem('overte.browser.graphics.v1');
            if(saved!==null){if(saved.length>1024)throw Error('Invalid stored graphics settings');graphicsWorld.graphics.apply(validateBrowserGraphics(JSON.parse(saved)));}
        } catch {log('Saved graphics settings could not be restored.','warning');}
        graphics=new BrowserGraphicsController(graphicsWorld.graphics,
            revision=>generation===epoch && world===graphicsWorld && ready && revision===permissionRevision,
            settings=>visitorStorage.setItem('overte.browser.graphics.v1',JSON.stringify(settings)));
        audio = new BrowserAudio(data => session.sendAudio(data), log, muted => {
            session.send({type:'mute', muted});
            updateMicrophone();
        });
        tablet = new BrowserTablet(element('app'), {
            send: message => session.send(message), onStatus: message => log(message, 'warning'),
            onGraphics:request=>graphics?.receive(request,request.revision),
            fileURL: name => {
                if (!session.sessionId) throw new Error('Join a world before accessing visitor files');
                return `/api/tablet-files/${encodeURIComponent(session.sessionId)}${name === undefined ? '' : `?name=${encodeURIComponent(name)}`}`;
            },
            captureScene: () => world ? world.captureScene() : Promise.reject(new Error('Join a world before taking a snapshot')),
            onVisibility: visible => {
                world?.setInputEnabled(!visible); world?.setPresentationEnabled(!visible);
                tabletButton.setAttribute('aria-pressed', String(visible));
            },
            onMicrophoneRequest: muted => {
                if (!ready || !audio || audio.muted === muted) return;
                if (muted) { audio.stopMicrophone(); session.send({type:'mute', muted:true}); updateMicrophone(); }
                else micButton.click();
            },
        });
        // Create/resume the audio context within the join gesture for browser autoplay policy.
        await audio.start().catch(error => log(`Audio unavailable: ${error.message}`, 'warning'));
        const response = await fetch('/api/session', {credentials:'same-origin', cache:'no-store'});
        if (!response.ok) throw new Error(`Gateway returned HTTP ${response.status}`);
        if (generation !== epoch) return;
        visitorPersona.update({displayName:nameInput.value.trim()});
        session.join(domain, nameInput.value.trim(),visitorPreferences.snapshot(),visitorPersona.snapshot());
    } catch (error) {
        if (generation !== epoch) return;
        reset();
        log(`Unable to join: ${error instanceof Error ? error.message : String(error)}`, 'error');
    }
}
form.addEventListener('submit', event => {
    event.preventDefault();
    void joinDomain(domainInput.value.trim());
});
element('leave').addEventListener('click', () => { reset(); log('You left the domain. Microphone and session stopped.'); });
tabletButton.addEventListener('click', () => { if (tablet?.visible) tablet.close(); else tablet?.open(); });
window.addEventListener('keydown', event => {
    if (event.code !== 'KeyT' || event.repeat || event.ctrlKey || event.metaKey || event.altKey
        || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
    if (ready) { event.preventDefault(); if (tablet?.visible) tablet.close(); else tablet?.open(); }
});
micButton.addEventListener('click', async () => {
    if (!ready || !audio || microphonePending) return;
    if (!audio.muted) {
        audio.stopMicrophone();
        session.send({type:'mute', muted:true});
        log('Microphone muted.');
        updateMicrophone();
        return;
    }
    const generation = epoch;
    const currentAudio = audio;
    microphonePending = true;
    updateMicrophone();
    const enabled = await currentAudio.enableMicrophone();
    if (generation !== epoch) return;
    session.send({type:'mute', muted:!enabled});
    microphonePending = false;
    updateMicrophone();
});
soundButton.addEventListener('click', async () => {
    if (!audio) return;
    const currentAudio = audio;
    const generation = epoch;
    await currentAudio.start().catch(error => log(error.message, 'error'));
    if (generation !== epoch || currentAudio !== audio) return;
    currentAudio.setSound(!currentAudio.sound);
    soundButton.textContent = currentAudio.sound ? 'Sound on' : 'Sound off';
    soundButton.setAttribute('aria-pressed', String(currentAudio.sound));
});
places.addEventListener('change', () => { if (places.value) domainInput.value = places.value; });
window.addEventListener('pagehide', reset);
void fetch('/api/config', {cache:'no-store'}).then(async response => {
    if (!response.ok) throw new Error('Gateway configuration unavailable.');
    const config = await response.json();
    if (Array.isArray(config.domains)) for (const place of config.domains) {
        if (typeof place.address !== 'string') continue;
        const option = document.createElement('option');
        option.value = place.address;
        option.textContent = place.name || place.address;
        places.append(option);
    }
    if (!domainInput.value && config.domains?.[0]?.address) {
        domainInput.value = config.domains[0].address;
        places.value = domainInput.value;
    }
}).catch(error => log(`${error.message} Start the self-hosted gateway to see available domains.`, 'warning'));

// Read-only diagnostics for repeatable journey tests; contains no credentials.
Object.defineProperty(window, '__overte', {value:{
    get connected() { return session.connected; },
    get pose() { return world?.getPose(); },
    get entityCount() { return entityCount; },
    get avatarCount() { return avatarCount; },
    get audio() { return audio?.stats; },
    get performance() { return world?.getPerformance(); },
    get graphics() { return world?.graphics.snapshot(); },
    get tabletVisible() { return tablet?.visible ?? false; },
    get avatarRig() { return world?.getSelfAvatarRig(); },
    get avatarRender() { return world?.getSelfAvatarRenderState(); },
    get renderInventory() { return world?.getRenderInventory(); },
    drawCensus() { return world?.getDrawCensus(); },
    drawCensusAsync() { return world?.getDrawCensusAsync(); },
}, configurable:true});
