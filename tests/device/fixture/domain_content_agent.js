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
        if (!Entities.serversExist() || !Entities.canRez()) {
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
        seeded = true;
        reportReady();
        print("OVERTE_E2E_DOMAIN_FIXTURE_READY markers=" + markers.length);
    }

    seed();
}());
