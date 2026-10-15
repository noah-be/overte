// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
'use strict';

// Exercise the changed proxy matching through the package's own dependencies.
// HTTP requests stay on an ephemeral IPv4 loopback listener; no AWS is involved.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {createRequire} = require('node:module');

function dependencies(directory) {
    const root = fs.realpathSync(path.resolve(directory));
    assert(fs.statSync(root).isDirectory(), 'package directory must exist');
    const localRequire = createRequire(path.join(root, 'package.json'));
    const modules = fs.realpathSync(path.join(root, 'node_modules')) + path.sep;
    for (const name of ['proxy-addr', 'express']) {
        assert(fs.realpathSync(localRequire.resolve(name)).startsWith(modules),
            'dependency must resolve inside the selected package node_modules');
    }
    return {proxyaddr: localRequire('proxy-addr'), express: localRequire('express')};
}

function request(port, forwarded) {
    return new Promise((resolve, reject) => {
        const outgoing = http.get({hostname: '127.0.0.1', port, path: '/ip', agent: false,
            headers: {'x-forwarded-for': forwarded}}, response => {
            let bytes = 0, body = '';
            response.setEncoding('utf8');
            response.on('data', chunk => {
                bytes += Buffer.byteLength(chunk);
                if (bytes > 4096) {
                    outgoing.destroy(new Error('bounded loopback response exceeded its limit'));
                } else {
                    body += chunk;
                }
            });
            response.on('error', reject);
            response.on('end', () => {
                try {
                    assert.equal(response.statusCode, 200);
                    resolve(JSON.parse(body));
                } catch (error) {
                    reject(error);
                }
            });
        });
        outgoing.setTimeout(3000, () => outgoing.destroy(new Error('loopback request timed out')));
        outgoing.on('error', reject);
    });
}

async function expressForwarding(express, trust, forwarded, expected) {
    const app = express();
    app.disable('x-powered-by');
    app.set('trust proxy', trust);
    app.get('/ip', (req, res) => res.json({ip: req.ip, ips: req.ips}));
    const server = app.listen(0, '127.0.0.1');
    try {
        await new Promise((resolve, reject) => {
            server.once('listening', resolve);
            server.once('error', reject);
        });
        const address = server.address();
        assert(address && typeof address === 'object' && address.address === '127.0.0.1');
        assert.deepEqual(await request(address.port, forwarded), expected);
    } finally {
        server.closeAllConnections();
        await new Promise((resolve, reject) => server.close(error => {
            if (error && error.code !== 'ERR_SERVER_NOT_RUNNING') reject(error);
            else resolve();
        }));
    }
}

async function main() {
    assert.equal(process.argv.length, 3, 'usage: node npm-proxy-addr-tests.cjs <package-directory>');
    const {proxyaddr, express} = dependencies(process.argv[2]);
    const vectors = [
        ['::/1', '192.0.2.7', false],
        ['::/1', '::ffff:192.0.2.7', false],
        ['::/1', '2001:db8::7', true],
        ['::/1', '::1', true],
        ['2001:db8::/32', '::ffff:192.0.2.7', false],
        ['2001:db8::/32', '2001:db8:1::7', true],
        ['2001:db8::/32', '2001:db9::7', false],
        ['192.0.2.0/24', '192.0.2.7', true],
        ['192.0.2.0/24', '::ffff:192.0.2.7', true],
        ['192.0.2.0/24', '192.0.3.7', false],
        ['192.0.2.0/24', '2001:db8::7', false],
        ['::ffff:192.0.2.0/120', '192.0.2.7', true],
        ['::ffff:192.0.2.0/120', '::ffff:192.0.2.7', true],
        ['::ffff:192.0.2.0/120', '192.0.3.7', false],
        ['::ffff:192.0.2.0/120', '2001:db8::7', false],
        ['::ffff:0:0/80', '192.0.2.7', false],
        ['::ffff:0:0/80', '::ffff:192.0.2.7', false],
        ['::ffff:0:0/80', '::1', false],
        ['192.0.2.0/24', 'not-an-ip', false],
    ];
    let trustChecks = 0;
    for (const [subnet, candidate, expected] of vectors) {
        // One subnet and several subnets use different upstream trust functions.
        for (const subnets of [[subnet], [subnet, '198.18.0.0/15']]) {
            const trust = proxyaddr.compile(subnets);
            assert.equal(trust(candidate), expected, 'unexpected trust for ' + candidate + ' in ' + subnets.join(','));
            trustChecks++;
        }
    }

    const forwarded = {socket: {remoteAddress: '192.0.2.7'},
        headers: {'x-forwarded-for': '203.0.113.9, 198.51.100.7'}};
    const ipv6Only = proxyaddr.compile('::/1');
    assert.equal(proxyaddr(forwarded, ipv6Only), '192.0.2.7');
    assert.deepEqual(proxyaddr.all(forwarded, ipv6Only), ['192.0.2.7']);
    const explicitChain = proxyaddr.compile(['192.0.2.0/24', '198.51.100.0/24']);
    assert.equal(proxyaddr(forwarded, explicitChain), '203.0.113.9');
    assert.deepEqual(proxyaddr.all(forwarded, explicitChain),
        ['192.0.2.7', '198.51.100.7', '203.0.113.9']);

    const spoofed = '203.0.113.9';
    await expressForwarding(express, false, spoofed, {ip: '127.0.0.1', ips: []});
    await expressForwarding(express, '::/1', spoofed, {ip: '127.0.0.1', ips: []});
    await expressForwarding(express, '::ffff:0:0/80', spoofed, {ip: '127.0.0.1', ips: []});
    await expressForwarding(express, '127.0.0.0/8', spoofed, {ip: spoofed, ips: [spoofed]});
    await expressForwarding(express, '::ffff:127.0.0.0/104', spoofed,
        {ip: spoofed, ips: [spoofed]});
    await expressForwarding(express, ['127.0.0.0/8', '198.51.100.0/24'],
        '203.0.113.9, 198.51.100.7', {ip: spoofed, ips: [spoofed, '198.51.100.7']});

    process.stdout.write(JSON.stringify({profile: 'proxy-addr-express-v1', trustChecks,
        forwardedChainChecks: 4, loopbackHttpChecks: 6, status: 'passed'}) + '\n');
}

main().catch(error => {
    process.stderr.write('proxy-addr/Express behavior checks failed: ' + String(error.message).slice(0, 2000) + '\n');
    process.exitCode = 1;
});
