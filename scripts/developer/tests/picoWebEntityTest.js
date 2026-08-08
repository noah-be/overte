// Local, dependency-free Web Entity acceptance panel for Pico controller input.
(function () {
    "use strict";

    var entityID = null;
    var html = [
        "<!doctype html><meta name='viewport' content='width=device-width'>",
        "<style>",
        "*{box-sizing:border-box}body{margin:0;background:#087f5b;color:#fff;font:32px sans-serif}",
        "main{height:900px;padding:36px;overflow-y:scroll}h1{margin:0 0 24px;color:#6de5ff}",
        ".target{padding:28px;border:6px solid #396273;border-radius:18px;margin:20px 0;background:#183747}",
        ".target:hover{border-color:#ffe66d;background:#275468}",
        "button{width:100%;padding:30px;font-size:36px;background:#168aad;color:white;border:0;border-radius:14px}",
        "button:hover{background:#52b69a}input{width:100%;height:70px}",
        ".spacer{height:600px;background:linear-gradient(#183747,#5c2b59);padding:30px}",
        "#goal{padding:35px;background:#d1495b;font-weight:bold;text-align:center}",
        "</style><main><h1>Pico Web Entity Test</h1>",
        "<div class='target'>Hover target</div>",
        "<button id='button'>Clicks: <span id='count'>0</span></button>",
        "<div class='target'>Slider: <span id='value'>50</span><input id='slider' type='range' value='50'></div>",
        "<div class='spacer'>Hold the trigger and use the hand thumbstick to scroll down.</div>",
        "<div id='goal'>SCROLL GOAL REACHED</div></main>",
        "<script>",
        "let count=0;button.onclick=()=>{count.textContent=++count};",
        "slider.oninput=()=>{value.textContent=slider.value};",
        "</script>"
    ].join("");

    function createPanel() {
        var position = Vec3.sum(Camera.position,
            Vec3.multiply(Quat.getForward(Camera.orientation), 1.8));
        entityID = Entities.addEntity({
            type: "Web",
            name: "Pico Local Web Entity Test",
            sourceUrl: "data:text/html;charset=utf-8," + encodeURIComponent(html),
            position: position,
            rotation: Camera.orientation,
            drawInFront: true,
            dimensions: { x: 1.6, y: 1.2, z: 0.02 },
            dpi: 16,
            maxFPS: 10,
            locked: false,
            grab: { grabbable: false },
            userData: JSON.stringify({ grabbableKey: { grabbable: false } })
        }, "local");
        print("[picoWebEntityTest] Created local panel " + entityID);
    }

    function cleanup() {
        if (entityID) {
            Entities.deleteEntity(entityID);
            entityID = null;
        }
    }

    createPanel();
    Script.scriptEnding.connect(cleanup);
}());
