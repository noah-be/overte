// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Bounded passive native pose observation at an event boundary. The qualified
 * identity is used transiently, never emitted. Raw null/default values and
 * exact finite selected joints are copied without conversion or mutation. */
export function createAvatarEventObserver(expectedNativeID) {
    const canonical = value => typeof value === 'string' && /^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value)
        && value.startsWith('{') === value.endsWith('}') ? value.replace(/[{}-]/g, '').toLowerCase() : null;
    const identity = canonical(expectedNativeID);
    if (!identity || /^0+$/.test(identity)) throw new Error('A privately qualified native participant is required.');
    const counts = { avatarEvents: 0, emptyEvents: 0, ambiguousEvents: 0, unmatchedEvents: 0,
        invalidPosition: 0, samples: 0, positionChanges: 0, jointPoseChanges: 0, sampleEvictions: 0 };
    const samples = [], names = ['Hips', 'Head', 'LeftArm', 'RightArm'];
    let first = null, last = null, lastJoints;
    const finite = (value, components) => value && components.every(key => typeof value[key] === 'number' && Number.isFinite(value[key]))
        ? Object.fromEntries(components.map(key => [key, value[key]])) : null;
    const copy = value => value ? JSON.parse(JSON.stringify(value)) : null;
    function accept(event) {
        if (event?.type !== 'avatars' || !Array.isArray(event.avatars)) return;
        counts.avatarEvents++;
        if (event.avatars.length === 0) { counts.emptyEvents++; return; }
        if (event.avatars.length !== 1) { counts.ambiguousEvents++; return; }
        const avatar = event.avatars[0];
        if (canonical(avatar?.id) !== identity) { counts.unmatchedEvents++; return; }
        const position = finite(avatar.position, ['x', 'y', 'z']);
        if (!position) { counts.invalidPosition++; return; }
        const joints = {}, jointNames = Array.isArray(avatar.jointNames) ? avatar.jointNames : [];
        for (const name of names) {
            const index = jointNames.slice(0, 256).indexOf(name);
            if (index < 0) { joints[name] = { present: false }; continue; }
            const rotation = avatar.jointRotations?.[index], translation = avatar.jointTranslations?.[index];
            joints[name] = { present: true, index, rotationDefaultFlag: rotation === null,
                translationDefaultFlag: translation === null,
                rotation: finite(rotation, ['x', 'y', 'z', 'w']), translation: finite(translation, ['x', 'y', 'z']),
                nativeParent: Number.isSafeInteger(avatar.jointParents?.[index]) ? avatar.jointParents[index] : null,
                defaultRotation: finite(avatar.jointDefaultRotations?.[index], ['x', 'y', 'z', 'w']),
                defaultTranslation: finite(avatar.jointDefaultTranslations?.[index], ['x', 'y', 'z']),
                defaultScale: Number.isFinite(avatar.jointDefaultScales?.[index]) ? avatar.jointDefaultScales[index] : null };
        }
        const currentJoints = JSON.stringify(joints), sample = { atMs: performance.now(), observedAtUnixMs: Date.now(),
            position, nativeIdentityMatched: true, jointCount: Math.min(jointNames.length, 256),
            jointCountTruncated: jointNames.length > 256, joints };
        if (last && ['x', 'y', 'z'].some(axis => last.position[axis] !== position[axis])) counts.positionChanges++;
        if (lastJoints !== undefined && lastJoints !== currentJoints) counts.jointPoseChanges++;
        lastJoints = currentJoints; counts.samples++;
        if (!first) first = copy(sample);
        last = copy(sample);
        if (samples.length >= 64) { samples.shift(); counts.sampleEvictions++; }
        samples.push(sample);
    }
    return Object.freeze({ accept, snapshot: () => ({ ...counts, limits: { retainedSamples: 64, selectedJoints: 4, jointNameSearch: 256 },
        scope: 'Actual single privately matched native peer at this event boundary; four raw nullable joint poses/defaults, no coordinate conversion.',
        first: copy(first), last: copy(last), retained: samples.map(copy) }) });
}
