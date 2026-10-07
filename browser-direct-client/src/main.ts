// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted implementation; provenance and verification are recorded in REUSE.md.
import './styles.css';
import { BrowserWorld } from './world';
import { BrowserAudio } from './audio';
import { LocalTablet } from './local-tablet';
import { WorkerDirectSession } from './worker-direct-session';
import { browserIdentity } from './local-tablet-data';
import { defaultAvatarAsset } from './default-avatar';
import { DEFAULT_BROWSER_GRAPHICS } from '../shared/browser-graphics.mjs';
import type { Avatar, Entity } from './world-data';
import type { BrowserIdentity, SessionEvent } from './session-contract';

function required<T extends HTMLElement>(selector: string): T {
    const result = document.querySelector<T>(selector);
    if (!result) throw Error(`Missing application element: ${selector}`);
    return result;
}
const container = required('#world'), notice = required('#notice'), connection = required('#connection');
const assetWarning = required('#asset-warning');
const microphoneButton = required<HTMLButtonElement>('#microphone'), tabletButton = required<HTMLButtonElement>('#tablet-toggle');
let world: BrowserWorld | undefined, tablet: LocalTablet | undefined, selfId = '', avatars: Avatar[] = [];
let state = 'disconnected', receivedEntities = 0;
const storageKey = 'overte.direct.identity.v1';
let identity: BrowserIdentity = { displayName: 'Browser visitor', skeletonModelURL: 'qrc:/meshes/defaultAvatar_full.fst', scale: 1 };
try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || 'null') as BrowserIdentity | null;
    if (saved) identity = browserIdentity(saved.displayName, saved.skeletonModelURL, saved.scale);
} catch { /* Unavailable storage or invalid old preferences do not prevent joining. */ }

function status(message: string, kind = 'info'): void {
    notice.textContent = message; notice.dataset.kind = kind;
}
const audio = new BrowserAudio(frame => session.sendAudio(frame), status, muted => {
    tablet?.setMicrophone(muted);
    microphoneButton.textContent = muted ? 'Microphone off' : 'Microphone on';
    microphoneButton.setAttribute('aria-pressed', String(!muted));
});
const session = new WorkerDirectSession({ event: receive, audio: frame => audio.receive(frame) });
let audioPortAttachment: Promise<void> | undefined;
async function startAudio(): Promise<void> {
    await audio.start();
    if (audio.stats.transport === 'worker') return;
    audioPortAttachment ??= audio.attachAudioPort(session.createAudioPort()).catch(error => {
        audioPortAttachment = undefined; throw error;
    });
    await audioPortAttachment;
}

function createWorld(): void {
    assetWarning.hidden = true; assetWarning.textContent = '';
    try {
        world = new BrowserWorld(container, {
            imageCaching: new URL(window.location.href).searchParams.get('benchmarkImageCache') !== 'off',
            resolveAsset: asset => defaultAvatarAsset(asset, window.location.href) || session.assetURL(asset),
            resolveAssetSource: asset => session.resolveAssetSource(asset),
            captureAssetAuthority: () => session.captureAssetAuthority(),
            onPose: pose => session.sendPose(pose),
            onInteract: entity => interact(entity),
            onStatus: status,
            onIncompleteTextures: ({ unavailableTextures, incompleteModels }) => {
                assetWarning.hidden = unavailableTextures === 0;
                assetWarning.textContent = unavailableTextures ? `${unavailableTextures} texture${unavailableTextures === 1 ? '' : 's'} unavailable. ${incompleteModels} object${incompleteModels === 1 ? '' : 's'} remain${incompleteModels === 1 ? 's' : ''} visible with incomplete textures.` : '';
            },
        });
        world.setInputEnabled(!(tablet?.visible ?? true));
    } catch (error) {
        status(`The world could not start: ${error instanceof Error ? error.message : String(error)}`, 'error');
    }
}
function resetWorld(): void {
    world?.dispose(); world = undefined; selfId = ''; avatars = []; receivedEntities = 0;
    audio.stopMicrophone(); audio.resetPlayback();
    tablet?.setPeople([]); createWorld();
}
function renderAvatars(): void {
    if (!world) return;
    const peers = avatars.filter(avatar => avatar.id !== selfId);
    if (selfId) {
        const pose = world.getPose();
        peers.push({ id: selfId, displayName: identity.displayName, position: pose.position,
            orientation: pose.orientation, scale: identity.scale, skeletonModelURL: identity.skeletonModelURL });
    }
    world.setAvatars(peers); tablet?.setPeople(peers, selfId);
}
function receive(event: SessionEvent): void {
    switch (event.type) {
        case 'status':
            if (event.state === 'connecting' && state !== 'connecting') resetWorld();
            state = event.state;
            connection.textContent = state[0].toUpperCase() + state.slice(1); connection.dataset.state = state;
            tablet?.setConnection(event.state, event.message);
            microphoneButton.disabled = event.state !== 'connected';
            world?.setEnabled(event.state === 'connected');
            if (event.state === 'connected') {
                session.sendIdentity(identity); renderAvatars();
                status(event.message || 'Connected. The world is loading; close the tablet to explore.');
            } else if (event.state === 'disconnected' || event.state === 'error') {
                audio.stopMicrophone(); audio.resetPlayback();
                world?.setEntities([]); world?.setAvatars([]); avatars = []; selfId = ''; tablet?.setPeople([]);
                status(event.message || 'Disconnected. Choose a domain to join again.', event.state === 'error' ? 'error' : 'info');
            } else status(event.message || 'Connecting to the domain…');
            break;
        case 'entities':
            world?.setEntities(event.entities); receivedEntities = event.entities.length;
            status(`Received ${receivedEntities} entities. Models and textures are loading on this device.`); break;
        case 'upserts': world?.upsertEntities(event.entities); break;
        case 'remove': world?.removeEntities(event.ids); break;
        case 'avatars': avatars = event.avatars; renderAvatars(); break;
        case 'localAvatar': selfId = event.id; world?.setLocalAvatar(event.id); renderAvatars(); break;
        case 'spawn': world?.setSpawn(event.position, event.orientation); break;
        case 'permissions': tablet?.setPermissions(event.permissions); break;
        case 'microphoneMuted': audio.stopMicrophone(); status('The domain audio mixer muted your microphone.', 'warning'); break;
        case 'error': status(event.message, 'error'); break;
    }
}
function interact(entity: Entity): void {
    tablet?.selectEntity(entity); session.sendInteraction(entity.id);
    status(`Selected ${entity.name || entity.type}.`, 'info');
}
async function microphone(enabled: boolean): Promise<boolean> {
    if (!session.connected) { status('Join a domain before enabling your microphone.', 'warning'); return false; }
    if (enabled) {
        try { await startAudio(); return await audio.enableMicrophone(); }
        catch (error) { status(error instanceof Error ? error.message : 'Voice could not start.', 'error'); return false; }
    }
    audio.stopMicrophone(); status('Microphone muted.'); return true;
}
async function connect(endpoint: string): Promise<void> {
    if (!world) throw Error('WebGL is unavailable. Enable browser graphics support and reload.');
    // Playback begins from this explicit visitor gesture. Capture is separate.
    try { await startAudio(); } catch (error) { status(error instanceof Error ? error.message : String(error), 'warning'); }
    await session.connect(endpoint);
}
createWorld();
tablet = new LocalTablet(required('#tablet'), {
    connect,
    leave: () => session.leave(),
    reconnect: async () => { await startAudio(); await session.reconnect(); },
    identity: value => {
        identity = value; session.sendIdentity(value); renderAvatars();
        try { localStorage.setItem(storageKey, JSON.stringify(value)); status('Avatar preferences applied and saved.'); }
        catch { status('Avatar preferences applied. This browser could not save them.', 'warning'); }
    },
    microphone,
    sound: enabled => audio.setSound(enabled),
    graphics: () => world?.graphics.snapshot() ?? { ...DEFAULT_BROWSER_GRAPHICS },
    applyGraphics: value => { if (!world) throw Error('The world renderer is unavailable.'); world.graphics.apply(value); },
    snapshot: () => world?.captureScene() ?? Promise.reject(Error('Join a world before taking a snapshot.')),
    thirdPerson: enabled => world?.setThirdPerson(enabled),
    visible: visible => { world?.setInputEnabled(!visible); tabletButton.setAttribute('aria-expanded', String(visible)); },
    onStatus: status,
}, identity, new URL(window.location.href).searchParams.get('server') || '');
microphoneButton.disabled = true;
microphoneButton.addEventListener('click', () => { void microphone(audio.muted); });
tabletButton.addEventListener('click', () => tablet?.toggle());
window.addEventListener('keydown', event => {
    if (event.code === 'KeyT' && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) tablet?.toggle();
});
window.addEventListener('pagehide', () => { session.dispose(); world?.dispose(); tablet?.dispose(); void audio.dispose(); });

/** Read-only acceptance diagnostics: no credentials or server session tokens. */
Object.defineProperty(window, 'overteDirectDiagnostics', {
    value: () => ({ state, assetRouting: session.assetRouting, entities: world?.entityCount ?? 0, receivedEntities, pose: world?.getPose(),
        participants: avatars.length, participantGeometry: world?.getParticipantGeometry(), selfAvatar: world?.getSelfAvatarRenderState(),
        selfRig: world?.getSelfAvatarRig(), zoneSkybox: world?.getZoneSkyboxDiagnostics(), performance: world?.getPerformance(), audio: audio.stats,
        tablet: { visible: tablet?.visible, app: tablet?.activeApp, selectedEntityID: tablet?.selectedEntityID } }),
});
Object.defineProperty(window, 'overteObserveEntityRendering', {
    value: (ids: readonly string[], maximumMs?: number) => {
        if (!world) return Promise.reject(new Error('The browser world is unavailable'));
        return world.observeEntityRendering(ids, maximumMs);
    },
});
Object.defineProperty(window, 'overteObserveAvatarRendering', {
    value: (ids: readonly string[], maximumMs?: number) => {
        if (!world) return Promise.reject(new Error('The browser world is unavailable'));
        return world.observeAvatarRendering(ids, maximumMs);
    },
});
Object.defineProperty(window, 'overteInspectCollision', { value: () => world?.getCollisionEvidence() });
Object.defineProperty(window, 'overteInspectView', { value: () => world?.getViewEvidence() });
Object.defineProperty(window, 'overteModelLoadEvidence', { value: (limit?: number) => world?.getModelLoadStates(limit) });
