// SPDX-License-Identifier: Apache-2.0
import { constants } from 'node:fs';
import { open } from 'node:fs/promises';

// Serialized by page.evaluate: keep this function self-contained. The actual
// assertion consumes these exact avatars, never a later browser/native sample.
export function captureNativePeerSnapshot({ fixtureName, target }) {
    const audio = window.__labAudio;
    const snapshot = audio.snapshots.filter(value => value.type === 'avatars').at(-1);
    const avatars = snapshot?.avatars;
    const arrivedAt = snapshot && audio.snapshotTimes.get(snapshot);
    const age = typeof arrivedAt === 'number' ? performance.now() - arrivedAt : NaN;
    const distance = position => position && [position.x, position.y, position.z].every(value => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e7)
        ? Math.hypot(position.x - target.x, position.y - target.y, position.z - target.z) : null;
    const peers = Array.isArray(avatars) ? avatars.filter(avatar => avatar.id !== snapshot.selfId) : [];
    const delivery=audio.delivery, selected=delivery && snapshot && delivery.snapshotSockets.get(snapshot);
    const ready=value=>[0,1,2,3].includes(value)?['connecting','open','closing','closed'][value]:'unknown';
    const socketSelection=delivery ? {selectedSocketOrdinal:selected?.ordinal ?? null,latestCreatedSocketOrdinal:delivery.censored?null:delivery.sockets,
        selectedIsLatest:selected ? selected.socket===delivery.latestSocket : null,
        selectedReadyState:selected?ready(selected.socket.readyState):'unknown',latestReadyState:ready(delivery.latestSocket?.readyState),
        ordinalCensored:delivery.censored} : null;
    return { avatars, diagnostic: {
        ...(delivery ? {socketSelection} : {}),
        snapshotPresent: !!snapshot,
        snapshotAgeMs: Number.isFinite(age) && age >= 0 && age <= 1e9 ? age : null,
        avatarCount: Array.isArray(avatars) ? avatars.length : 0,
        peerCount: peers.length,
        fixtureNameMatchCount: peers.filter(avatar => avatar.displayName === fixtureName).length,
        peerProjectionTruncated: peers.length > 16,
        peers: peers.slice(0, 16).map(avatar => ({ fixtureNameMatch: avatar.displayName === fixtureName,
            targetDistance: distance(avatar.position) }))
    } };
}

const MAX_TAIL_BYTES = 1024 * 1024;
const finiteTimestamp = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e15 ? value : null;
const distance = (position, target) => position && [position.x, position.y, position.z].every(value => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e7)
    ? Math.hypot(position.x - target.x, position.y - target.y, position.z - target.z) : null;

// Pure whitelist projection; no record or untrusted string is returned.
export function projectNativePeerLog(text, { sequence, target, now = Date.now() }) {
    let applied, observation;
    for (const line of text.split('\n')) {
        const marker = line.indexOf('BROWSER_LAB ');
        if (marker < 0) continue;
        let record;
        try { record = JSON.parse(line.slice(marker + 'BROWSER_LAB '.length)); } catch { continue; }
        if (record?.kind === 'command-applied' && record.data?.sequence === sequence && record.data?.position) applied = record;
        if (record?.kind === 'observation' && record.data?.position) observation = record;
    }
    const commandAppliedAtMs = finiteTimestamp(applied?.at);
    const observationAtMs = finiteTimestamp(observation?.at);
    const age = stamp => stamp !== null && finiteTimestamp(now) !== null && now >= stamp ? now - stamp : null;
    return {
        status: 'read', commandSequenceMatched: !!applied,
        commandIssuedAtMs: applied ? finiteTimestamp(sequence) : null, diagnosticReadAtMs: finiteTimestamp(now),
        commandAppliedAtMs, commandAppliedAgeMs: age(commandAppliedAtMs),
        commandTargetDistance: applied ? distance(applied.data.position, target) : null,
        observationPresent: !!observation, observationAtMs, observationAgeMs: age(observationAtMs),
        observationAfterCommand: commandAppliedAtMs !== null && observationAtMs !== null ? observationAtMs >= commandAppliedAtMs : null,
        observationTargetDistance: observation ? distance(observation.data.position, target) : null
    };
}

// One read after capture. Missing/refused/unparseable diagnostics cannot alter
// the already captured movement predicate. No waits or retries; no symlink open,
// regular-file-only, and at most one MiB from the fstat-captured tail.
export async function readNativePeerDiagnostic(filename, operation) {
    let handle;
    try {
        handle = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
        const metadata = await handle.stat();
        if (!metadata.isFile() || !Number.isSafeInteger(metadata.size) || metadata.size < 0) return { status: 'not-regular' };
        const offset = Math.max(0, metadata.size - MAX_TAIL_BYTES);
        const buffer = Buffer.alloc(Math.min(metadata.size, MAX_TAIL_BYTES));
        const { bytesRead } = await handle.read(buffer, 0, buffer.length, offset);
        let text = buffer.subarray(0, bytesRead).toString('utf8');
        if (offset > 0) { const newline = text.indexOf('\n'); text = newline < 0 ? '' : text.slice(newline + 1); }
        return { ...projectNativePeerLog(text, operation), bytesRead, tailTruncated: offset > 0 };
    } catch (error) {
        return { status: error?.code === 'ENOENT' ? 'missing' : error?.code === 'ELOOP' ? 'symlink-refused' : 'read-refused' };
    } finally { try { await handle?.close(); } catch {} }
}
