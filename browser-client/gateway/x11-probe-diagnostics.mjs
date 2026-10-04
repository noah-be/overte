// SPDX-License-Identifier: Apache-2.0
// Test-only projection of the already-observed first X11 reply; no new wire query.
export function x11ProbeDiagnostic(kind, value) {
    if (kind === 'timeout') return { kind: 'timeout' };
    if (kind === 'socket-error') return { kind, errno: ['EACCES', 'EPERM', 'ENOENT', 'ECONNREFUSED', 'ECONNRESET', 'EPIPE'].includes(value?.code) ? value.code : 'other-error' };
    if (kind !== 'setup' || !Buffer.isBuffer(value)) return { kind: 'invalid-observation' };
    const status = value[0];
    if (status === 1) return { kind: 'setup', status: 'accepted' };
    if (status !== 0 && status !== 2) return { kind: 'setup', status: 'invalid' };
    const length = value.length >= 8 ? value[1] : 0;
    const reason = value.subarray(8, 8 + length).toString('latin1');
    const reasons = new Map([
        ['Invalid MIT-MAGIC-COOKIE-1 key', 'invalid-cookie'],
        ['Authorization required, but no authorization protocol specified', 'authorization-required'],
        ['No protocol specified', 'authorization-required'],
        ['Client is not authorized to connect to Server', 'not-authorized'],
        ['Maximum number of clients reached', 'client-limit'],
        ['Protocol version mismatch', 'protocol-version-mismatch'],
    ]);
    return { kind: 'setup', status: status === 0 ? 'refused' : 'authenticate',
        reason: value.length >= 8 + length && value.length >= 8 ? reasons.get(reason.trim()) || 'unrecognized' : 'unrecognized', reasonBytes: length,
        incomplete: value.length < 8 + length || value.length < 8 };
}
