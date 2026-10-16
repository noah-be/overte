// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
'use strict';

// Dependency behavior probes, loaded from the explicitly selected npm package.
// This file does not build the Browser client or run its unrelated test inventory.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {spawnSync} = require('node:child_process');

function dependencies(directory) {
    const root = fs.realpathSync(path.resolve(directory));
    assert(fs.statSync(root).isDirectory(), 'package directory must exist');
    const localRequire = createRequire(path.join(root, 'package.json'));
    const modules = fs.realpathSync(path.join(root, 'node_modules')) + path.sep;
    for (const name of ['source-map-js', 'postcss']) {
        assert(fs.realpathSync(localRequire.resolve(name)).startsWith(modules),
            'dependency must resolve inside the selected package node_modules');
    }
    return {root, sourceMap: localRequire('source-map-js'), postcss: localRequire('postcss')};
}

function flatMap(SourceMapGenerator, {line = 1, source = 'input.js'} = {}) {
    const map = new SourceMapGenerator({file: 'output.js'});
    map.addMapping({generated: {line, column: 0}, original: {line: 1, column: 0}, source});
    map.setSourceContent(source, 'const value = 1;\n');
    return map.toJSON();
}

function indexed(map, line = 0, column = 0) {
    return {version: 3, sections: [{offset: {line, column}, map}]};
}

function mappingOrder({SourceMapConsumer, SourceMapGenerator}) {
    const generator = new SourceMapGenerator({file: 'sorted.js'});
    // Original order differs from generated order, exercising consumer sorting.
    generator.addMapping({generated: {line: 2, column: 0}, original: {line: 1, column: 0}, source: 'a.js'});
    generator.addMapping({generated: {line: 1, column: 0}, original: {line: 2, column: 0}, source: 'a.js'});
    const consumer = new SourceMapConsumer(generator.toJSON());
    const generated = [], original = [];
    consumer.eachMapping(row => generated.push([row.generatedLine, row.originalLine]));
    consumer.eachMapping(row => original.push([row.generatedLine, row.originalLine]),
        null, SourceMapConsumer.ORIGINAL_ORDER);
    assert.deepEqual(generated, [[1, 2], [2, 1]]);
    assert.deepEqual(original, [[2, 1], [1, 2]]);
}

async function main() {
    assert(process.argv.length === 3 || process.argv.length === 4,
        'usage: node npm-source-map-tests.cjs <package-directory> [--no-eval-child]');
    const {root, sourceMap, postcss} = dependencies(process.argv[2]);
    const {SourceMapConsumer, SourceMapGenerator, SourceNode} = sourceMap;
    if (process.argv.length === 4) {
        assert.equal(process.argv[3], '--no-eval-child', 'unsupported probe argument');
        assert.throws(() => new Function('return 0'), EvalError,
            'the sorting child must actually prohibit string code generation');
        mappingOrder(sourceMap);
        process.stdout.write('no-eval source-map sorting passed\n');
        return;
    }

    const checks = [];
    function check(name, run) {
        try {
            run();
        } catch (error) {
            throw new Error(name + ': ' + String(error.message), {cause: error});
        }
        checks.push(name);
    }

    check('flat-and-indexed-map-positions-and-content', () => {
        const flat = flatMap(SourceMapGenerator);
        for (const [map, line] of [[flat, 1], [indexed(flat, 3), 4], [indexed(indexed(flat, 2), 3), 6]]) {
            const consumer = new SourceMapConsumer(map);
            assert.deepEqual(consumer.sources, ['input.js']);
            assert.equal(consumer.sourceContentFor('input.js'), 'const value = 1;\n');
            assert.deepEqual(consumer.originalPositionFor({line, column: 1}),
                {source: 'input.js', line: 1, column: 0, name: null});
        }
        const flattened = SourceMapGenerator.fromSourceMap(new SourceMapConsumer(flat)).toJSON();
        assert.deepEqual(new SourceMapConsumer(flattened).originalPositionFor({line: 1, column: 1}),
            {source: 'input.js', line: 1, column: 0, name: null});
    });

    check('invalid-and-excessive-section-offsets-rejected-before-expansion', () => {
        const flat = flatMap(SourceMapGenerator);
        for (const value of [-1, 0.5, '1', NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, null, undefined]) {
            const lineMap = indexed(flat), columnMap = indexed(flat);
            lineMap.sections[0].offset.line = value;
            columnMap.sections[0].offset.column = value;
            assert.throws(() => new SourceMapConsumer(lineMap), /offset/i);
            assert.throws(() => new SourceMapConsumer(columnMap), /offset/i);
        }
        assert.throws(() => new SourceMapConsumer(indexed(flat, 10_000_001)), /offset/i);
        // Constructor validation must reject this tiny input before flattening
        // it could allocate one separator per combined generated line.
        assert.throws(() => new SourceMapConsumer(indexed(indexed(flat, 4_000_001), 6_000_000)),
            /offset/i);
    });

    check('nested-source-enumeration-has-bounded-work', () => {
        const generator = new SourceMapGenerator({file: 'two-sources.js'});
        for (const [index, source] of ['first.js', 'second.js'].entries()) {
            generator.addMapping({generated: {line: index + 1, column: 0},
                original: {line: 1, column: 0}, source});
        }
        let map = generator.toJSON();
        for (let depth = 0; depth < 6; depth++) map = indexed(map);
        const consumer = new SourceMapConsumer(map);
        // Observe reads at the already-created leaf, without implementing map
        // enumeration ourselves. Repeated public .sources access used to grow
        // exponentially through nested indexed maps.
        let leaf = consumer;
        for (let depth = 0; depth < 6; depth++) leaf = leaf._sections[0].consumer;
        const getter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(leaf), 'sources').get;
        let reads = 0;
        Object.defineProperty(leaf, 'sources', {get() { reads++; return getter.call(this); }});
        assert.deepEqual(consumer.sources, ['first.js', 'second.js']);
        assert(reads <= 2, 'one source listing must not repeatedly enumerate the nested leaf');
    });

    check('moderate-line-gap-serialization-roundtrips', () => {
        const generator = new SourceMapGenerator({file: 'gap.js'});
        for (const [generated, original] of [[1, 1], [4096, 2]]) {
            generator.addMapping({generated: {line: generated, column: 0},
                original: {line: original, column: 0}, source: 'input.js'});
        }
        const map = generator.toJSON();
        assert.equal(map.mappings.split(';').length, 4096);
        assert(map.mappings.length < 4200, 'bounded line-gap fixture grew unexpectedly');
        assert.deepEqual(new SourceMapConsumer(map).originalPositionFor({line: 4096, column: 0}),
            {source: 'input.js', line: 2, column: 0, name: null});
    });

    check('source-node-stops-work-after-generated-code-exhaustion', () => {
        const consumer = new SourceMapConsumer(flatMap(SourceMapGenerator, {line: 4096}));
        const originalAdd = SourceNode.prototype.add;
        let additions = 0;
        try {
            SourceNode.prototype.add = function (...args) {
                additions++;
                return originalAdd.apply(this, args);
            };
            const node = SourceNode.fromStringWithSourceMap('x', consumer);
            assert.equal(node.toString(), 'x');
            assert(additions <= 4, 'exhausted input must not cause an add for every absent generated line');
        } finally {
            SourceNode.prototype.add = originalAdd;
        }
    });

    check('normal-and-no-eval-consumer-sorting', () => {
        mappingOrder(sourceMap);
        const child = spawnSync(process.execPath, ['--disallow-code-generation-from-strings', __filename,
            root, '--no-eval-child'], {encoding: 'utf8', timeout: 10_000, maxBuffer: 16_384,
            env: {...process.env, NODE_OPTIONS: ''}});
        assert.ifError(child.error);
        assert.equal(child.signal, null, 'no-eval sorting child was terminated');
        assert.equal(child.status, 0, 'no-eval sorting child failed: ' + child.stderr.slice(0, 1000));
        assert.equal(child.stdout, 'no-eval source-map sorting passed\n');
    });

    const css = 'a { color: red; }\n';
    const generated = await postcss([]).process(css, {from: 'input.css', to: 'output.css',
        map: {inline: false, annotation: false}});
    assert.equal(generated.css, css);
    assert(generated.map, 'PostCSS must generate a real source map');
    const previous = generated.map.toJSON();
    assert.deepEqual(previous.sources, ['input.css']);
    assert.deepEqual(previous.sourcesContent, [css]);
    const mapped = new SourceMapConsumer(previous).originalPositionFor({line: 1, column: 0});
    assert.equal(mapped.source, 'input.css');
    assert.equal(mapped.line, 1);
    checks.push('actual-postcss-map-generation');

    const roundtrip = await postcss([]).process(css, {from: 'output.css', to: 'roundtrip.css',
        map: {inline: false, annotation: false, prev: JSON.stringify(previous)}});
    assert.equal(roundtrip.css, css);
    assert(roundtrip.map, 'PostCSS must consume and re-emit the prior map');
    const remapped = new SourceMapConsumer(roundtrip.map.toJSON()).originalPositionFor({line: 1, column: 0});
    assert.equal(remapped.source, 'input.css');
    assert.equal(remapped.line, 1);
    checks.push('actual-postcss-prior-map-roundtrip');
    await assert.rejects(async () => {
        const result = await postcss([]).process(css, {from: 'output.css', to: 'rejected.css',
            map: {inline: false, annotation: false,
                prev: JSON.stringify(indexed(indexed(previous, 4_000_001), 6_000_000))}});
        // Force any lazy map generation while all offsets remain constructor-bound.
        result.map.toJSON();
    }, /offset/i);
    checks.push('actual-postcss-invalid-nested-prior-map-rejected');

    process.stdout.write(JSON.stringify({profile: 'source-map-postcss-v1', checks, status: 'passed'}) + '\n');
}

main().catch(error => {
    process.stderr.write('source-map/PostCSS behavior checks failed: ' + String(error.message).slice(0, 2000) + '\n');
    process.exitCode = 1;
});
