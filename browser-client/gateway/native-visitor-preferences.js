// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted ES5 adapter. Only reviewed bookmark values enter the private worker.
function createBrowserVisitorPreferences(config) {
    var restored = false, stopped = false, lastPoll = 0, lastSignature = '', lastAuthority = null, warned = false;
    function snapshot() {
        var raw = config.api.getBookmarks(), names = Object.keys(raw), bookmarks = [];
        if (names.length > 101) { throw new Error('The native bookmark collection exceeds the browser limit of 100.'); }
        names.sort().forEach(function (name) {
            if (name !== 'Home') { bookmarks.push({ name: String(name), address: String(raw[name]) }); }
        });
        var result = { bookmarks: bookmarks }, home = String(config.api.getHomeLocationAddress() || '');
        if (home) { result.home = home; }
        return result;
    }
    function restore() {
        if (stopped || restored || !config.authority()) { return; }
        // No account, settings file or operator profile is read or copied.
        Object.keys(config.api.getBookmarks()).forEach(function (name) { config.api.removeBookmark(name); });
        var initial = config.initial || { bookmarks: [] };
        initial.bookmarks.forEach(function (bookmark) { // The packaged native Places UI recognizes the legacy domain scheme.
            config.api.addBookmark(bookmark.name, bookmark.address.replace(/^overte:/, 'hifi:')); });
        // Native insert() treats an empty address as a real reserved Home row.
        // Leave it absent until the visitor explicitly saves a Home location.
        if (initial.home) { config.api.setHomeLocationToAddress(initial.home.replace(/^overte:/, 'hifi:')); }
        restored = true;
    }
    function poll(force) {
        var authority = config.authority(), now = Date.now();
        if (stopped || !authority || !restored || (!force && now - lastPoll < 1000)) { return; }
        lastPoll = now;
        try {
            var preferences = snapshot(), signature = JSON.stringify(preferences);
            if (signature === lastSignature && authority === lastAuthority) { return; }
            // The bridge also checks authority again when its engine outbox drains.
            if (config.authority() !== authority) { return; }
            lastSignature = signature; lastAuthority = authority;
            config.send({ type: 'visitorPreferences', permissionRevision: config.revision(),
                bookmarks: preferences.bookmarks, home: preferences.home });
        } catch (error) {
            if (!warned) { warned = true; config.send({ type: 'warning', message: 'Native bookmarks could not be saved within the browser preference limits.' }); }
        }
    }
    return { restore: restore, poll: poll, stop: function () { stopped = true; } };
}
