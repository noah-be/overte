"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { createScriptApi, runProductionScript } = require("../support");

function fixture(t) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "script-include-"));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    fs.mkdirSync(path.join(root, "nested"));
    const write = (name, source) => {
        const filename = path.join(root, name);
        fs.writeFileSync(filename, source);
        return filename;
    };
    return { root, write };
}

test("includes execute real nested files once, in the wrapper's VM and path context", (t) => {
    const { root, write } = fixture(t);
    write("nested/late.js", "events.push(\'late\');");
    write("nested/leaf.js", "events.push('leaf'); var fromLeaf = shared + 1;");
    const included = write("nested/implementation.js", `
        events.push('implementation');
        var asset = Script.resolvePath('asset.svg');
        Script.include(Script.resolvePath('leaf.js'));
        var lateAsset;
        Script.scriptEnding.connect(function () {
            lateAsset = Script.resolvePath('late.svg');
            Script.include('late.js');
            events.push(fromLeaf);
        });
    `);
    const wrapper = write("wrapper.js", `
        var shared = 6;
        Script.include(['nested/implementation.js', 'nested/implementation.js']);
        events.push(fromLeaf);
        Script.include('nested/implementation.js', function () { events.push('callback'); });
    `);
    const Script = createScriptApi();
    const events = [];
    const execution = runProductionScript(wrapper, { Script, events });
    assert.deepEqual(events, ['implementation', 'leaf', 7]);
    assert.equal(execution.context.asset, path.join(root, 'nested/asset.svg'));
    assert.deepEqual(execution.loadedFiles, [wrapper, included, path.join(root, 'nested/leaf.js')]);
    assert.equal(Script.runTimer(1), true);
    assert.equal(events.at(-1), 'callback');
    Script.end();
    assert.equal(events.at(-1), 7);
    assert.equal(execution.context.lateAsset, path.join(root, 'nested/late.svg'));
    assert.equal(execution.loadedFiles.at(-1), path.join(root, 'nested/late.js'));
    assert.equal(events.at(-2), 'late');
    const secondEvents = [];
    runProductionScript(wrapper, { Script: createScriptApi(), events: secondEvents });
    assert.deepEqual(secondEvents, ['implementation', 'leaf', 7], 'include cache must not leak between VMs');
});

test("missing or invalid included sources fail the harness instead of passing empty mocks", (t) => {
    const { write } = fixture(t);
    const Script = createScriptApi();
    assert.throws(() => Script.include('missing.js'), /production VM loader/);
    const missing = write('missing-wrapper.js', "Script.include('missing.js');");
    assert.throws(() => runProductionScript(missing, { Script }), /ENOENT/);
    write('invalid.js', 'var = ;');
    const invalid = write('invalid-wrapper.js', "Script.include('invalid.js');");
    assert.throws(() => runProductionScript(invalid, { Script }), /Unexpected token/);
});

test("mutation replaces the included implementation while retaining the real wrapper", (t) => {
    const { write } = fixture(t);
    const included = write('implementation.js', 'var result = 1;');
    const wrapper = write('wrapper.js', "var wrapperRan = true; Script.include('implementation.js');");
    const mutant = write('mutant.js', 'var result = 2;');
    const previous = [process.env.OVERTE_MUTATION_TARGET, process.env.OVERTE_MUTATION_SOURCE];
    t.after(() => {
        for (const [index, name] of ['OVERTE_MUTATION_TARGET', 'OVERTE_MUTATION_SOURCE'].entries()) {
            if (previous[index] === undefined) delete process.env[name];
            else process.env[name] = previous[index];
        }
    });
    process.env.OVERTE_MUTATION_TARGET = included;
    process.env.OVERTE_MUTATION_SOURCE = mutant;
    const execution = runProductionScript(wrapper, { Script: createScriptApi() });
    assert.equal(execution.context.result, 2);
    assert.equal(execution.context.wrapperRan, true);
    assert.deepEqual(execution.loadedFiles, [wrapper, included]);
    delete process.env.OVERTE_MUTATION_SOURCE;
    assert.throws(() => runProductionScript(wrapper, { Script: createScriptApi() }), /supplied together/);
});
