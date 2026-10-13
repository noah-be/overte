// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
(function () {
    if (window !== window.top || window.__overteTransport) { return; }
    var queue = [], listeners = [], grant = "0", page = "0", authorized = false;
    var transport = { onmessage: null, send: function (message) {
        if (typeof message !== "string" || message.length > 65536) { return; }
        if (!authorized) { if (queue.length < 64) { queue.push(message); } return; }
        window.__overteNative.postMessage(JSON.stringify({ grant: grant, page: page,
            type: "channel", payload: message }));
    }};
    window.qt = { webChannelTransport: transport };
    window.__overteTransport = {
        authorize: function (nextGrant, nextPage) {
            grant = String(nextGrant); page = String(nextPage); authorized = true;
            var pending = queue; queue = [];
            pending.forEach(transport.send);
        },
        suspend: function () { authorized = false; queue = []; },
        receive: function (expectedGrant, expectedPage, message) {
            if (authorized && String(expectedGrant) === grant && String(expectedPage) === page
                    && typeof transport.onmessage === "function") {
                transport.onmessage({ data: JSON.stringify(message) });
            }

        }
    };
}());
