'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const test = require('node:test');
const cheerio = require('cheerio');
const request = require('@cypress/request');

test('request replacement preserves callback and stream APIs', async function(t) {
    var server = http.createServer(function(req, res) {
        res.writeHead(200, { 'content-type': 'text/plain' });
        res.end('overte');
    });
    await new Promise(function(resolve, reject) {
        server.listen(0, '127.0.0.1', resolve);
        server.once('error', reject);
    });
    t.after(function() {
        server.close();
    });
    var address = server.address();
    var target = 'http://127.0.0.1:' + address.port + '/';

    var body = await new Promise(function(resolve, reject) {
        request.get(target, function(error, response, responseBody) {
            if (error) {
                reject(error);
            } else {
                assert.equal(response.statusCode, 200);
                resolve(responseBody);
            }
        });
    });

    assert.equal(body, 'overte');
    var streamRequest = request.get(target);
    assert.equal(typeof streamRequest.pipe, 'function');
    streamRequest.abort();
});

test('Cheerio still parses the build-feed selectors used by the updater', function() {
    var xml = '<projects><project name="interface"><platform name="windows">' +
        '<build><stable_version>1.2.3</stable_version><url>https://example.test/build</url></build>' +
        '</platform></project></projects>';
    var $ = cheerio.load(xml, { xmlMode: true });
    var latestBuild = $('project[name="interface"] platform[name="windows"]').children().first();

    assert.equal(latestBuild.find('stable_version').text(), '1.2.3');
    assert.equal(latestBuild.find('url').text(), 'https://example.test/build');
});
