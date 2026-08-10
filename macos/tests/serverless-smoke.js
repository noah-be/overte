// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    var deadline = Date.now() + 30000;
    var snapshotRequested = false;
    var completed = false;

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        print("OVERTE_MACOS_SMOKE " + (success ? "passed " : "failed ") + detail);
        Test.quit();
    }

    Window.stillSnapshotTaken.connect(function (path) {
        finish(Boolean(path), "snapshot=" + path);
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        if (entities.length > 0 && !snapshotRequested) {
            snapshotRequested = true;
            print("OVERTE_MACOS_SMOKE entities=" + entities.length);
            Window.takeSnapshot(false, false, 16 / 9);
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotRequested ? "snapshot_timeout" : "entity_timeout");
        }
    }, 250);
}());
