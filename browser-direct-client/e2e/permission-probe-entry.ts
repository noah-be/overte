// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Isolated real permission/component diagnostic. Production source is unchanged.
import { BrowserAudio } from '../src/audio';

const streams: MediaStream[] = [], notices: { message: string; kind?: string }[] = [];
let nativeRequests = 0, nativeErrorName = '', enableTrusted = false, stopTrusted = false;
let enabled: boolean | undefined, disposed = false, permissionBefore: PermissionState | undefined;
let capturedCallbacks = 0, phase = 'idle';
const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
// Observe the real API's exact return values. Never supply a permission answer,
// replace a stream, change constraints or retain device identifiers/PCM.
navigator.mediaDevices.getUserMedia = async constraints => {
    nativeRequests++;
    try {
        const stream = await originalGetUserMedia(constraints);
        if (streams.length < 1) streams.push(stream);
        return stream;
    } catch (error) {
        nativeErrorName = error instanceof DOMException ? error.name : 'Error';
        throw error;
    }
};
const audio = new BrowserAudio(buffer => {
    if (buffer.byteLength === 480) capturedCallbacks++;
}, (message, kind) => {
    if (notices.length < 8) notices.push({ message, kind });
    document.querySelector('#status')!.textContent = message;
});
const permission = async () => (await navigator.permissions.query({ name: 'microphone' as PermissionName })).state;
const state = async () => ({ phase, permissionBefore, permission: await permission(), nativeRequests,
    nativeErrorName, enabled, enableTrusted, stopTrusted, disposed, notices: notices.map(value => ({ ...value })),
    returnedStreams: streams.length, returnedAudioTracks: streams.reduce((sum, stream) => sum + stream.getAudioTracks().length, 0),
    liveAudioTracks: streams.flatMap(stream => stream.getAudioTracks()).filter(track => track.readyState === 'live').length,
    allReturnedTracksStopped: streams.every(stream => stream.getTracks().every(track => track.readyState === 'ended')),
    capturedCallbacks, audio: { ...audio.stats }, deviceIdentifiersRetained: false, labelsRetained: false, pcmRetained: false });
const dispose = async () => {
    await audio.dispose(); disposed = true; phase = 'stopped';
    return state();
};
document.querySelector('#enable')!.addEventListener('click', async event => {
    if (phase !== 'idle') return;
    enableTrusted = event.isTrusted; phase = 'requesting';
    permissionBefore = await permission();
    enabled = await audio.enableMicrophone(); phase = 'answered';
});
document.querySelector('#stop')!.addEventListener('click', async event => {
    stopTrusted = event.isTrusted; await dispose();
});
declare global {
    interface Window { overtePermissionProbe: { state: typeof state; dispose: typeof dispose } }
}
window.overtePermissionProbe = { state, dispose };
window.addEventListener('pagehide', () => { void dispose(); });
