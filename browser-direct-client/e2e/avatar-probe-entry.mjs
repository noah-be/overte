// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Isolated actual WorkerDirectSession entry. No World/model/image imports.
import { WorkerDirectSession } from '../src/worker-direct-session.ts';
import { createAvatarEventObserver } from './avatar-event-evidence.mjs';

let observer;
const evidence = { state: 'disconnected', entityCount: 0, avatarCount: 0, audioFrames: 0,
    spawn: null, localAvatarReceived: false, lastError: '', automaticSceneAssetRequests: 0 };
const sanitized = value => String(value).replace(/\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b/gi, '[identifier]')
    .replace(/\b(?:https?|wss?):\/\/[^\s"'<>]+/gi, '[endpoint]').slice(0, 600);
const session = new WorkerDirectSession({
    event(event) {
        // This is the actual public façade callback, before any cached World.
        observer?.accept(event);
        if (event.type === 'status') evidence.state = event.state;
        if (event.type === 'entities') evidence.entityCount = event.entities.length;
        if (event.type === 'avatars') evidence.avatarCount = event.avatars.length;
        if (event.type === 'localAvatar') evidence.localAvatarReceived = true;
        if (event.type === 'error') evidence.lastError = sanitized(event.message);
        if (event.type === 'spawn') {
            evidence.spawn = { ...event.position };
            // Publish the actual domain-selected spawn, without a test teleport.
            session.sendPose({ position: { ...event.position }, orientation: event.orientation || { x: 0, y: 0, z: 0, w: 1 }, velocity: { x: 0, y: 0, z: 0 } });
        }
    },
    audio() { evidence.audioFrames++; },
});
const probe = Object.freeze({
    configure(expectedNativeID) {
        if (observer || evidence.state !== 'disconnected') throw new Error('Configure the qualified peer exactly once before Join.');
        observer = createAvatarEventObserver(expectedNativeID);
    },
    async join(endpoint) {
        if (!observer) throw new Error('Configure the qualified native peer before Join.');
        await session.connect(endpoint);
        session.sendIdentity({ displayName: 'avatar-probe-chromium', skeletonModelURL: location.origin + '/default-avatar/defaultAvatar_full.fst', scale: 1 });
        return this.state();
    },
    state() { return { ...evidence, spawn: evidence.spawn ? { ...evidence.spawn } : null,
        callbackBoundary: 'Actual WorkerDirectSession SessionCallbacks.event before any renderer', facadeEvents: observer?.snapshot() }; },
    leave() { session.leave(); },
});
Object.defineProperty(window, 'overteAvatarProbe', { value: probe });
window.addEventListener('pagehide', () => session.dispose(), { once: true });
