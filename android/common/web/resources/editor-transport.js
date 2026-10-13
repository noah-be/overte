// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
(function () {
    if (window !== window.top || window.__overteEditorTransport) { return; }
    var grant = "0", page = "0", authorized = false;
    window.__overteEditorTransport = {
        authorize: function (nextGrant, nextPage) {
            grant = String(nextGrant); page = String(nextPage); authorized = true;
        },
        suspend: function () { authorized = false; },
        editor: function (state) {
            if (authorized) {
                window.__overteEditorNative.postMessage(JSON.stringify({ grant: grant,
                    page: page, payload: state }));
            }
        }
    };
}());
