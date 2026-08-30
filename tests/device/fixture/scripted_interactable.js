// Repository-owned client entity script for scripted-entity-smoke.
(function () {
    "use strict";

    var entityId = null;
    var contract = "overte-e2e-scripted-entity-v1";
    var active = false;
    var activationCount = 0;
    var idleColor = { red: 255, green: 150, blue: 40 };
    var activeColor = { red: 40, green: 220, blue: 100 };

    function publish() {
        Entities.editEntity(entityId, {
            color: active ? activeColor : idleColor,
            userData: JSON.stringify({
                contract: contract,
                loaded: true,
                state: active ? "active" : "idle",
                activationCount: activationCount
            })
        });
    }

    this.preload = function (id) {
        entityId = id;
        publish();
    };

    this.clickDownOnEntity = function (id) {
        if (String(id) !== String(entityId)) {
            return;
        }
        activationCount += 1;
        active = !active;
        publish();
    };
});
