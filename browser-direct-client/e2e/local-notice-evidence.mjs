// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Test-only UI observation. Retain added text nodes rather than the final DOM
 * text, so multiple notices in one microtask cannot erase a model failure. */
export function observeLocalNotices() {
    const events = []; let count = 0, evicted = 0, firstEntityFailure;
    const sanitize = value => {
        const bounded = String(value).slice(0, 4096);
        if (/\b(password|authorization|secret|sdp|candidate|token)\b/i.test(bounded)) return '[Sensitive notice omitted]';
        return bounded.replace(/\b(?:https?|wss?):[^\s"'<>]+/gi, value => {
            try { const url = new URL(value); url.username = ''; url.password = ''; url.search = ''; url.hash = ''; return url.href; }
            catch { return '[Invalid endpoint omitted]'; }
        });
    };
    const retain = message => {
        if (!message?.trim()) return;
        const event = { atMs: performance.now(), message: sanitize(message) };
        count++;
        if (!firstEntityFailure && /^Could not load /i.test(event.message)) firstEntityFailure = event;
        if (events.length >= 128) { events.shift(); evicted++; }
        events.push(event);
    };
    const install = () => {
        const notice = document.getElementById('notice'); if (!notice) return;
        retain(notice.textContent);
        new MutationObserver(records => {
            for (const record of records) if (record.type === 'childList' && record.target === notice) {
                for (const node of record.addedNodes) retain(node.textContent);
            }
        }).observe(notice, { childList: true });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
    else install();
    Object.defineProperty(window, 'overteLocalNoticeEvidence', { value: () => ({
        events: events.map(event => ({ ...event })), count, retained: events.length, limit: 128, evicted,
        firstEntityFailure: firstEntityFailure ? { ...firstEntityFailure } : null,
        scope: 'Private test-only notice text, timing and sanitized source paths; no requests, protocol data or credentials.'
    }) });
}
