// Persistent assignment used only by the ephemeral E2E domain fixture.
(function () {
    "use strict";

    var contract = "overte-e2e-domain-v1";
    var retryMilliseconds = 250;
    var markers = [
        {
            name: "OVERTE_E2E_DOMAIN_FLOOR",
            type: "Box",
            position: { x: 0.0, y: -0.25, z: 0.0 },
            dimensions: { x: 20.0, y: 0.5, z: 20.0 },
            color: { red: 90, green: 90, blue: 90 }
        },
        {
            name: "OVERTE_E2E_DOMAIN_NORTH",
            type: "Box",
            position: { x: 0.0, y: 0.5, z: -3.0 },
            dimensions: { x: 0.5, y: 1.0, z: 0.5 },
            color: { red: 40, green: 120, blue: 255 }
        },
        {
            name: "OVERTE_E2E_DOMAIN_EAST",
            type: "Box",
            position: { x: 3.0, y: 0.5, z: 0.0 },
            dimensions: { x: 0.5, y: 1.0, z: 0.5 },
            color: { red: 40, green: 220, blue: 100 }
        },
        {
            name: "OVERTE_E2E_DOMAIN_ORIGIN",
            type: "Sphere",
            position: { x: 0.0, y: 0.5, z: 0.0 },
            dimensions: { x: 0.6, y: 0.6, z: 0.6 },
            color: { red: 255, green: 70, blue: 70 }
        }
    ];
    var seeded = false;
    var sharedName = "OVERTE_E2E_SHARED_COLOR";
    var actorId = "OVERTE_E2E_ACTOR_FIXTURE";
    var sharedEntity = null;
    var lastCommand = "seed";
    var requestInFlight = false;

    function colorFor(value) {
        return value === "blue" ? { red: 40, green: 120, blue: 255 }
            : { red: 255, green: 150, blue: 40 };
    }

    function reportShared(commandId, state) {
        var request = new XMLHttpRequest();
        request.open("POST", Script.resolvePath("actor-state"), true);
        request.setRequestHeader("Content-Type", "application/json");
        request.send(JSON.stringify({ schemaVersion: 1, commandId: commandId,
            actorSessionId: String(Agent.sessionUUID).replace(/[{}]/g, "").toLowerCase(),
            entityName: sharedName, actorId: actorId,
            revision: state.revision, value: state.value }));
    }

    function matchesShared(properties, revision, value) {
        var state;
        try { state = JSON.parse(properties.userData); } catch (error) { return false; }
        var color = colorFor(value);
        return properties.name === sharedName && state.contract === "overte-e2e-collaboration-v1"
            && state.actorId === actorId && state.revision === revision && state.value === value
            && properties.color && properties.color.red === color.red
            && properties.color.green === color.green && properties.color.blue === color.blue;
    }

    function pollShared() {
        if (!sharedEntity || requestInFlight) { return; }
        requestInFlight = true;
        var request = new XMLHttpRequest();
        request.open("GET", Script.resolvePath("actor-command"), true);
        request.onreadystatechange = function () {
            if (request.readyState !== 4) { return; }
            requestInFlight = false;
            if (request.status !== 200) { return; }
            var command;
            try { command = JSON.parse(request.responseText); } catch (error) { return; }
            if (command.pending === false) { return; }
            if (command.schemaVersion !== 1 || command.entityName !== sharedName
                    || command.actorSessionId !== String(Agent.sessionUUID).replace(/[{}]/g, "").toLowerCase()
                    || typeof command.commandId !== "string" || !/^[0-9a-f]{32}$/.test(command.commandId)
                    || typeof command.revision !== "number" || !isFinite(command.revision)
                    || command.revision < 1 || command.revision > 9007199254740991 || command.revision % 1 !== 0
                    || (command.value !== "blue" && command.value !== "orange")) { return; }
            var properties = Entities.getEntityProperties(sharedEntity, ["name", "userData", "color"]);
            var state;
            try { state = JSON.parse(properties.userData); } catch (error) { return; }
            if (properties.name !== sharedName || state.contract !== "overte-e2e-collaboration-v1"
                    || state.actorId !== actorId) { return; }
            if (command.commandId === lastCommand) {
                if (matchesShared(properties, command.revision, command.value)) {
                    reportShared(command.commandId, state);
                }
                return;
            }
            if (command.revision !== state.revision + 1) { return; }
            state.revision = command.revision;
            state.value = command.value;
            Entities.editEntity(sharedEntity, { color: colorFor(state.value), userData: JSON.stringify(state) });
            // Observe the actor's real entity state before acknowledging. The
            // client must separately observe the replication over the domain.
            Script.setTimeout(function () {
                var observed = Entities.getEntityProperties(sharedEntity, ["name", "userData", "color"]);
                try {
                    var actual = JSON.parse(observed.userData);
                    if (matchesShared(observed, command.revision, command.value)) {
                        lastCommand = command.commandId;
                        reportShared(command.commandId, actual);
                    }
                } catch (error) { /* The domain may be stopping. */ }
            }, retryMilliseconds);
        };
        request.send();
    }

    function reportReady() {
        var request = new XMLHttpRequest();
        request.open("POST", Script.resolvePath("domain-ready"), true);
        request.setRequestHeader("Content-Type", "application/json");
        request.send(JSON.stringify({ schemaVersion: 1, markerCount: markers.length }));
    }

    function seed() {
        if (seeded) {
            return;
        }
        if (!Entities.serversExist() || !Entities.canRez()
                || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(
                    String(Agent.sessionUUID).replace(/[{}]/g, "").toLowerCase())
                || String(Agent.sessionUUID).replace(/[{}]/g, "") === "00000000-0000-0000-0000-000000000000") {
            Script.setTimeout(seed, retryMilliseconds);
            return;
        }
        markers.forEach(function (marker) {
            var properties = marker;
            properties.description = contract;
            properties.userData = JSON.stringify({ contract: contract, marker: marker.name });
            properties.lifetime = 7200;
            Entities.addEntity(properties, "domain");
        });
        sharedEntity = Entities.addEntity({ name: sharedName, type: "Box",
            // Keep the replicated test entity in the spawn camera's view and
            // outside the movement lane so the entity server sends it.
            position: { x: 2, y: 0.5, z: -4 }, dimensions: { x: 0.5, y: 1, z: 0.5 },
            color: colorFor("blue"), lifetime: 7200,
            userData: JSON.stringify({ contract: "overte-e2e-collaboration-v1", actorId: actorId,
                revision: 0, value: "blue" }) }, "domain");
        reportShared("seed", { revision: 0, value: "blue" });
        Script.setInterval(pollShared, retryMilliseconds);
        seeded = true;
        reportReady();
        print("OVERTE_E2E_DOMAIN_FIXTURE_READY markers=" + markers.length);
    }

    seed();
}());
