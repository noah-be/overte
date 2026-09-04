const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");

test("macOS URL launch keeps hostile input in a single process argument", () => {
    const openUrl = require(path.join(root, "server-console/src/modules/open-url")).openUrl;
    const hostileUrl = "hifi://example/$(touch should-not-run);`id`";
    let invocation;
    openUrl("org.overte.interface", hostileUrl, (command, args) => {
        invocation = { command, args };
    });
    assert.deepEqual(invocation, {
        command: "open",
        args: ["-b", "org.overte.interface", "--args", "--url", hostileUrl]
    });
});

test("security-sensitive URL checks are origin or boundary aware", () => {
    const moreApplications = /^https:\/\/more\.overte\.org\/applications(?:[/?#]|$)/;
    assert.equal(moreApplications.test("https://more.overte.org/applications/tool.js"), true);
    assert.equal(moreApplications.test("https://evil.test/https://more.overte.org/applications"), false);
    assert.equal(moreApplications.test("https://more.overte.org/applications.evil.test/tool.js"), false);

    const expectedOrigin = "https://meta.test";
    assert.equal(new URL("https://meta.test/api/v1/places").origin, expectedOrigin);
    assert.notEqual(new URL("https://meta.test.evil.example/api/v1/places").origin, expectedOrigin);
});

test("CDN scripts in remediated HTML carry SHA-384 SRI and anonymous CORS", () => {
    const files = [
        "unpublishedScripts/marketplace/camera-move/app.html",
        "scripts/developer/utilities/render/photobooth/html/photobooth.html",
        "scripts/developer/tests/sliderTest.html"
    ];
    for (const file of files) {
        const html = read(file);
        const tags = html.match(/<script\b[^>]*\bsrc="https:\/\/[^>]+>/g) || [];
        assert.ok(tags.length > 0, `${file} must contain the expected CDN scripts`);
        for (const tag of tags) {
            assert.match(tag, /\bintegrity="sha384-[A-Za-z0-9+/=]+"/);
            assert.match(tag, /\bcrossorigin="anonymous"/);
        }
    }
});

test("unsafe dynamic execution and HTML reconstruction patterns stay removed", () => {
    assert.doesNotMatch(read("server-console/src/modules/hf-app.js"), /childProcess\.exec\s*\(/);
    assert.doesNotMatch(read("domain-server/resources/web/content/js/content.js"), /Math\.random\s*\(/);
    assert.doesNotMatch(read("domain-server/resources/web/assignment/js/ace/worker-javascript.js"), /main\s*\[\s*msg\.command\s*\]/);
    assert.match(read("domain-server/resources/web/assignment/js/ace/worker-javascript.js"), /msg\.module !== "ace\/mode\/javascript_worker"/);
    assert.match(read("domain-server/resources/web/assignment/js/ace/worker-javascript.js"), /msg\.classname !== "JavaScriptWorker"/);
    assert.doesNotMatch(read("scripts/system/html/users.html"), /\.html\s*\(\s*newButtonText/);
    const entityProperties = read("scripts/system/create/entityProperties/html/js/entityProperties.js");
    assert.doesNotMatch(entityProperties, /innerHTML\s*=\s*listed(?:Zone|Strings)Inner/);
    assert.match(entityProperties, /url\.indexOf\("https:\/\/"\) === 0/);
    assert.doesNotMatch(entityProperties, /url\.indexOf\("http:\/\/"\) === 0/);
    assert.match(entityProperties, /elImage\.src = encodeURI\(url\)/);
});

test("prototype-pollution guards cover every patched embedded component", () => {
    const files = [
        "scripts/communityScripts/libraries/vuetify/vuetify-v2.3.9.js",
        "tools/jsdoc/hifi-jsdoc-template/static/scripts/vuetify.js",
        "tools/jsdoc/hifi-jsdoc-template/static/scripts/vue_dev.js"
    ];
    for (const file of files) {
        const source = read(file);
        assert.match(source, /key === ['"]__proto__['"]/);
        assert.match(source, /key === ['"]constructor['"]/);
        assert.match(source, /key === ['"]prototype['"]/);
    }
});

test("Ace regular expressions retain semantics without ambiguous escapes", () => {
    const component = "mode";
    const moduleName = new RegExp("^" + component + "[-_]|[-_]" + component + "$", "g");
    assert.equal("mode-javascript".replace(moduleName, ""), "javascript");
    assert.equal("javascript_mode".replace(moduleName, ""), "javascript");

    const removeCharacterClasses = /\[(?:\\.|[^\]\\])*\]|\\.|\(\?[:=!]|(\()/g;
    const adversarial = "[" + "\\\\".repeat(10000);
    const started = performance.now();
    const result = adversarial.replace(removeCharacterClasses, "");
    assert.ok(performance.now() - started < 500, "regex processing should remain linear");
    assert.equal(result, "[");
});
