// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseServerMessage } from './session.ts';

test('real entity and avatar protocol messages retain native properties', () => {
    const value = {type:'entities',entities:[{id:'entity',type:'Model',modelURL:'atp:/test.glb',position:{x:1,y:2,z:3}}]};
    assert.deepEqual(parseServerMessage(JSON.stringify(value)), value);
    assert.deepEqual(parseServerMessage('{"type":"avatars","avatars":[{"id":"native","position":{"x":0,"y":1,"z":0}}]}').type, 'avatars');
});
test('malformed gateway state, identity and world data are rejected', () => {
    for (const message of [null, [], {}, {type:'unrecognized'}, {type:'state',state:'ready'},
        {type:'state',state:'connected',sessionId:'../../other'}, {type:'entities',entities:[{}]},
        {type:'avatars',avatars:[{id:'native',position:{x:'0',y:0,z:0}}]},
        {type:'pose',position:{x:0,y:null,z:0}}, {type:'error',message:42}]) {
        assert.throws(() => parseServerMessage(JSON.stringify(message)));
    }
});
