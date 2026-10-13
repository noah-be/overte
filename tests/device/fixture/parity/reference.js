// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
(function () {
    "use strict";
    var bridge = null, sequence = 0, waiting = null, imageUrl = null;
    function node(id) { return document.getElementById(id); }
    function show(id, message) { node(id).textContent = message; }
    show("document", "Loaded " + window.location.pathname + window.location.search);
    node("increment").onclick = function () { show("counter", String(Number(node("counter").textContent) + 1)); };
    ["text", "number", "password", "multiline"].forEach(function (id) {
        node(id).oninput = function () { show("inputStatus", id + ": " + this.value.length + " characters received"); };
    });
    node("scroll").onscroll = function () { show("scrollStatus", "Scroll position " + Math.round(this.scrollTop)); };
    node("file").onchange = function () {
        if (imageUrl) URL.revokeObjectURL(imageUrl);
        imageUrl = null;
        node("filePreview").style.display = "none";
        var file = this.files && this.files[0];
        show("fileStatus", file ? "Selected " + file.size + " bytes (" + (file.type || "unknown type") + ")" : "No file selected");
        if (file && /^image\//.test(file.type)) {
            imageUrl = URL.createObjectURL(file);
            // Keep file content in a blob and encode the URL for its DOM attribute context.
            node("filePreview").src = encodeURI(imageUrl);
            node("filePreview").style.display = "block";
        }
    };
    var video = node("video");
    function mediaState() { show("mediaStatus", (video.paused ? "Paused" : "Playing") + " at " + video.currentTime.toFixed(2) + " s · volume " + video.volume + (video.muted ? " · muted" : " · sound requested")); }
    ["loadedmetadata", "timeupdate", "play", "pause", "seeked", "ended"].forEach(function (event) { video.addEventListener(event, mediaState); });
    video.addEventListener("error", function () { show("mediaStatus", "Media error " + (video.error ? video.error.code : "unknown")); });
    node("play").onclick = function () {
        video.muted = false; video.volume = 1;
        var playing = video.play();
        if (playing && playing.catch) playing.catch(function (error) { show("mediaStatus", "Play failed: " + error.name); });
    };
    node("pause").onclick = function () { video.pause(); };
    node("seek").onclick = function () { video.currentTime = 4; };
    function receive(message) {
        var packet;
        try { packet = typeof message === "string" ? JSON.parse(message) : message; } catch (_) { return; }
        if (!packet || packet.contract !== "overte-web-parity-v1" || packet.action !== "echo" || packet.sequence !== waiting) return;
        waiting = null;
        show("bridgeStatus", "Real script echo received from " + packet.surface + " · sequence " + packet.sequence);
    }
    function acquireBridge() {
        var current = window.EventBridge;
        if (current === bridge || !current || typeof current.emitWebEvent !== "function" ||
                !current.scriptEventReceived || typeof current.scriptEventReceived.connect !== "function") return;
        bridge = current;
        bridge.scriptEventReceived.connect(receive);
    }
    node("bridge").onclick = function () {
        acquireBridge();
        if (!bridge) { show("bridgeStatus", "Native EventBridge unavailable"); return; }
        waiting = ++sequence;
        var sent = waiting;
        show("bridgeStatus", "Waiting for actual Overte script echo " + sent);
        bridge.emitWebEvent(JSON.stringify({contract: "overte-web-parity-v1", action: "echo", sequence: sent}));
        window.setTimeout(function () { if (waiting === sent) { waiting = null; show("bridgeStatus", "No script echo received (blocked, disconnected or unavailable)"); } }, 3000);
    };
    window.setInterval(function () {
        acquireBridge();
        if (window.overteParityInjectedCount) show("injection", "Actual source scriptUrl ran " + window.overteParityInjectedCount + " time(s) in this document");
    }, 250);
    node("back").onclick = function () { window.history.back(); };
    node("reload").onclick = function () { window.location.reload(); };
    node("navigate").onclick = function () {
        var target;
        try { target = new URL(node("foreign").value); } catch (_) { show("navigationStatus", "Enter the second controlled server URL."); return; }
        if (!/^https?:$/.test(target.protocol) || target.username || target.password || target.origin === window.location.origin) {
            show("navigationStatus", "Use a different controlled HTTP(S) origin without credentials."); return;
        }
        window.location.href = target.href;
    };
    // The native adapter must stop/silence the page on hide/background/close.
    // A cooperative JS pause would conceal a broken native lifecycle boundary.
    window.addEventListener("pagehide", function () { if (imageUrl) URL.revokeObjectURL(imageUrl); });
}());
