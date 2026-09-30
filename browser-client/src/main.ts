// SPDX-License-Identifier: Apache-2.0
import './style.css';
import { BrowserAudio } from './audio';
import { BrowserSession } from './session';
import type { ServerMessage } from './session';
import { BrowserWorld } from './world';

const element = <T extends HTMLElement>(id:string) => document.getElementById(id) as T;
const form = element<HTMLFormElement>('join-form');
const domainInput = element<HTMLInputElement>('domain');
const nameInput = element<HTMLInputElement>('name');
const joinButton = element<HTMLButtonElement>('join');
const places = element<HTMLSelectElement>('places');
const micButton = element<HTMLButtonElement>('microphone');
const soundButton = element<HTMLButtonElement>('sound');
const notice = element('notice');
let world: BrowserWorld | undefined;
let audio: BrowserAudio | undefined;
let epoch = 0;
let entityCount = 0;
let avatarCount = 0;
let joining = false;
let ready = false;
let worldLoaded = false;
let errorNotice = false;
let microphonePending = false;

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
    epoch++;
    session.leave();
    world?.dispose();
    world = undefined;
    void audio?.dispose();
    audio = undefined;
    joining = false;
    ready = false;
    worldLoaded = false;
    microphonePending = false;
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
                worldLoaded = false;
                world?.setEnabled(false);
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
            world?.setEntities(message.entities);
            entityCount = message.entities.length;
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
        case 'error': log(message.message, 'error'); break;
        case 'warning': log(message.message, 'warning'); break;
        case 'interaction': log(message.message); break;
    }
}
const session = new BrowserSession({
    message: onMessage,
    audio: data => audio?.receive(data),
    closed: reason => { reset(); if (!errorNotice) log(reason, 'warning'); },
    error: reason => log(reason, 'error'),
});

form.addEventListener('submit', async event => {
    event.preventDefault();
    if (joining) return;
    reset();
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
            onPose: pose => session.sendPose(pose),
            onInteract: entity => session.send({type:'interact', entityId:entity.id}),
            onStatus: log,
        });
        audio = new BrowserAudio(data => session.sendAudio(data), log, muted => {
            session.send({type:'mute', muted});
            updateMicrophone();
        });
        // Create/resume the audio context within the join gesture for browser autoplay policy.
        await audio.start().catch(error => log(`Audio unavailable: ${error.message}`, 'warning'));
        const response = await fetch('/api/session', {credentials:'same-origin', cache:'no-store'});
        if (!response.ok) throw new Error(`Gateway returned HTTP ${response.status}`);
        if (generation !== epoch) return;
        session.join(domainInput.value.trim(), nameInput.value.trim());
    } catch (error) {
        if (generation !== epoch) return;
        reset();
        log(`Unable to join: ${error instanceof Error ? error.message : String(error)}`, 'error');
    }
});
element('leave').addEventListener('click', () => { reset(); log('You left the domain. Microphone and session stopped.'); });
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
}, configurable:true});
