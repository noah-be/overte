'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const FileTail = require('../src/modules/file-tail');

function pollForLines(tail, expectedCount) {
    return new Promise(function(resolve, reject) {
        var lines = [];
        var timeout = setTimeout(function() {
            reject(new Error('Timed out while reading appended log lines'));
        }, 2000);
        tail.on('error', reject);
        tail.on('line', function(line) {
            lines.push(line);
            if (lines.length === expectedCount) {
                clearTimeout(timeout);
                resolve(lines);
            }
        });
        tail._poll();
    });
}

test('reads complete lines from the requested offset', async function(t) {
    var directory = fs.mkdtempSync(path.join(os.tmpdir(), 'overte-file-tail-'));
    var logPath = path.join(directory, 'server.log');
    fs.writeFileSync(logPath, 'old\nfirst\nsecond\n');
    t.after(function() {
        fs.rmSync(directory, { recursive: true, force: true });
    });

    var tail = new FileTail(logPath, '\n', { start: 4, interval: 10 });
    var lines = await pollForLines(tail, 2);

    assert.deepEqual(lines, ['first', 'second']);
    assert.equal(tail.position, fs.statSync(logPath).size);
});
