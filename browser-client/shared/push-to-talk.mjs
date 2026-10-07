// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
function base(value, type) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.type !== type || value.version !== 1
        || !Number.isSafeInteger(value.permissionRevision) || value.permissionRevision < 1
        || !Number.isSafeInteger(value.sequence) || value.sequence < 0) throw Error('Invalid native Push-to-Talk control.');
    return {type, version:1, permissionRevision:value.permissionRevision, sequence:value.sequence};
}
export function pushToTalkCommand(value) {
    const result=base(value,'pushToTalk');
    if (!result.sequence || typeof value.held !== 'boolean') throw Error('Invalid native Push-to-Talk control.');
    return {...result,held:value.held};
}
export function pushToTalkState(value) {
    const result=base(value,'pushToTalkState');
    if (['enabled','held','muted'].some(field=>typeof value[field] !== 'boolean')
        || value.held && !value.enabled) throw Error('Invalid native Push-to-Talk state.');
    return {...result,enabled:value.enabled,held:value.held,muted:value.muted};
}
