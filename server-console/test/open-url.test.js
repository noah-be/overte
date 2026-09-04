const assert = require('assert');
const openUrl = require('../src/modules/open-url').openUrl;

var invocation;
var hostileUrl = 'hifi://example/$(touch should-not-run);`id`';

openUrl('org.overte.interface', hostileUrl, function(command, args) {
    invocation = { command: command, args: args };
});

assert.deepStrictEqual(invocation, {
    command: 'open',
    args: ['-b', 'org.overte.interface', '--args', '--url', hostileUrl]
});
