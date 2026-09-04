'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const createApp = require('./index.js').createApp;

test('lists S3 object keys without contacting AWS', async function(t) {
    var observedInput;
    var fakeS3 = {
        send: async function(command) {
            observedInput = command.input;
            return {
                Contents: [
                    { Key: 'examples/one.js' },
                    { Key: 'examples/two.js' }
                ]
            };
        }
    };
    var server = createApp(fakeS3).listen(0, '127.0.0.1');
    await new Promise(function(resolve, reject) {
        server.once('listening', resolve);
        server.once('error', reject);
    });
    t.after(function() {
        server.close();
    });

    var address = server.address();
    var response = await fetch('http://127.0.0.1:' + address.port + '/?assetDir=examples%2F');

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {
        urls: ['examples/one.js', 'examples/two.js']
    });
    assert.deepEqual(observedInput, {
        Bucket: 'hifi-public',
        MaxKeys: 10,
        StartAfter: 'examples/'
    });
});
