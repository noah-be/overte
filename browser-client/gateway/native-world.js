// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// ES5-compatible, cooperatively scheduled native entity acquisition.
function createBrowserWorldStream(config) {
    'use strict';
    var generation = 0;
    var timer = null;
    var stopped = false;
    var running = false;
    var authority = null;
    var signatures = Object.create(null);
    var snapshotSent = false;
    var now = config.now || Date.now;
    var budget = Math.max(1, Math.min(12, config.budgetMs || 8));

    function reset() {
        generation++;
        if (timer !== null) { config.cancel(timer); timer = null; }
        running = false;
        authority = null;
        signatures = Object.create(null);
        snapshotSent = false;
    }
    function valid(cycle) {
        return !stopped && running && generation === cycle.generation && config.authority() === cycle.authority;
    }
    function abort(cycle) {
        if (generation === cycle.generation) { reset(); }
    }
    function fail(cycle) {
        if (generation !== cycle.generation) { return; }
        reset();
        config.onError('The native world could not be read safely. Leave and reconnect.');
    }
    function advance(cycle) {
        if (!valid(cycle)) { abort(cycle); return; }
        try {
            var started = now();
            var count = 0;
            while (cycle.index < cycle.ids.length && count < 64 && (count === 0 || now() - started < budget)) {
                if (!valid(cycle)) { abort(cycle); return; }
                var entity = config.readEntity(cycle.ids[cycle.index++]);
                count++;
                if (!valid(cycle)) { abort(cycle); return; }
                if (!entity || !entity.id || !entity.type) { continue; }
                var id = String(entity.id);
                var stable = {};
                Object.keys(entity).forEach(function (key) {
                    if (key !== 'age' && key !== 'ageAsText' && key !== 'renderInfo') { stable[key] = entity[key]; }
                });
                cycle.next[id] = JSON.stringify(stable);
                if (!snapshotSent) { cycle.entities.push(entity); }
                else if (cycle.next[id] !== signatures[id]) { cycle.changed.push(entity); }
            }
            if (!valid(cycle)) { abort(cycle); return; }
            if (cycle.index < cycle.ids.length) {
                var scheduled = config.schedule(function () {
                    if (timer === scheduled) { timer = null; }
                    advance(cycle);
                }, 16);
                timer = scheduled;
                return;
            }
            var removed = Object.keys(signatures).filter(function (id) {
                return !Object.prototype.hasOwnProperty.call(cycle.next, id);
            });
            if (!snapshotSent) { config.send({ type: 'entities', entities: cycle.entities }); }
            else if (cycle.changed.length || removed.length) {
                config.send({ type: 'entityUpdates', entities: cycle.changed, removed: removed });
            }
            // send may synchronously revoke a session in a test or embedding.
            if (!valid(cycle)) { abort(cycle); return; }
            signatures = cycle.next;
            snapshotSent = true;
            running = false;
        } catch (error) { fail(cycle); }
    }
    function poll() {
        if (stopped) { return; }
        var current = config.authority();
        if (!current) { reset(); return; }
        if (authority !== current) { reset(); authority = current; }
        if (running) { return; }
        var cycle = { generation: generation, authority: current, ids: [], index: 0,
            next: Object.create(null), entities: [], changed: [] };
        running = true;
        try {
            cycle.ids = config.readIDs();
            if (!Array.isArray(cycle.ids) || cycle.ids.length > 100000) { throw new Error('Invalid native entity collection'); }
            advance(cycle);
        } catch (error) { fail(cycle); }
    }
    return { poll: poll, reset: reset, stop: function () { stopped = true; reset(); } };
}
