// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import axios from 'axios';
import MessageData from '../src/protocol/vircadia/domain/networking/MessageData';
import MessagesData from '../src/protocol/vircadia/domain/networking/packets/MessagesData';
import DataServerAccountInfo from '../src/protocol/vircadia/domain/networking/DataServerAccountInfo';
import Socket from '../src/protocol/vircadia/domain/networking/udt/Socket';
import WebRTCSocket from '../src/protocol/vircadia/domain/networking/webrtc/WebRTCSocket';
import SockAddr from '../src/protocol/vircadia/domain/networking/SockAddr';
import NetworkAccessManager from '../src/protocol/vircadia/domain/networking/NetworkAccessManager';
import NetworkRequest from '../src/protocol/vircadia/domain/networking/NetworkRequest';
import Url from '../src/protocol/vircadia/domain/shared/Url';
import '../src/protocol/vircadia/domain/shared/DataViewExtensions';

test('native packet buffers retain only their view and clones cannot change the original', () => {
    const incoming = new Uint8Array([91, 92, 1, 2, 3, 93]), packet = new MessageData();
    packet.buffer = incoming.subarray(2, 5); packet.packetSize = 3;
    assert.deepEqual([...packet.buffer], [1, 2, 3]); assert.equal(packet.data.byteLength, 3);
    incoming.fill(0); assert.deepEqual([...packet.buffer], [1, 2, 3]);
    const clone = new MessageData(packet); clone.buffer[0] = 44;
    assert.deepEqual([...packet.buffer], [1, 2, 3]); assert.equal(clone.packetSize, 3);
});
test('binary MessagesData returns only the payload from a nonzero-offset native message', () => {
    const bytes = new Uint8Array(64).fill(90), view = new DataView(bytes.buffer, 5, 27);
    view.setUint16(0, 1, true); view.setUint8(2, 120); view.setUint8(3, 0); view.setUint32(4, 3, true);
    view.setUint8(8, 10); view.setUint8(9, 20); view.setUint8(10, 30);
    for (let index = 11; index < 27; index++) view.setUint8(index, 0);
    const message = MessagesData.read(view);
    assert.equal(message.channel, 'x'); assert.ok(message.message instanceof ArrayBuffer);
    assert.deepEqual([...new Uint8Array(message.message)], [10, 20, 30]);
    bytes.fill(0); assert.deepEqual([...new Uint8Array(message.message)], [10, 20, 30]);
});
test('UDT datagrams truncate byte views without exposing their surrounding allocation', t => {
    const delivered: ArrayBuffer[] = [];
    t.mock.method(WebRTCSocket.prototype, 'writeDatagram', (value: ArrayBuffer | Uint8Array) => {
        assert.ok(value instanceof ArrayBuffer); delivered.push(value); return value.byteLength;
    });
    const socket = new Socket(), address = new SockAddr(), bytes = new Uint8Array([99, 1, 2, 3, 98]);
    assert.equal(socket.writeDatagram(bytes.subarray(1, 4), 2, address), 2);
    assert.deepEqual([...new Uint8Array(delivered[0])], [1, 2]);
    assert.equal(socket.writeDatagram(bytes.buffer, -1, address), -1); assert.equal(delivered.length, 1);
});
test('native authentication signs owned plaintext and does not retain a caller-mutable private key', async () => {
    const key = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
    const encoded = new Uint8Array(await crypto.subtle.exportKey('pkcs8', key.privateKey));
    const account = new DataServerAccountInfo(); account.setPrivateKey(encoded); encoded.fill(0);
    const backing = new SharedArrayBuffer(8), shared = new Uint8Array(backing, 2, 3); shared.set([10, 20, 30]);
    const signature = await account.signPlaintext(shared);
    assert.equal(signature.byteLength, 256);
    assert.equal(await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key.publicKey,
        new Uint8Array(signature), new Uint8Array(shared)), true);
});
test('browser-native multipart authentication keeps strings and Blob filenames without a Node polyfill', async t => {
    let submitted: FormData | undefined;
    t.mock.method(axios, 'put', (url: string, data: FormData) => {
        submitted = data; return Promise.resolve({ config: { url }, headers: {}, data: {} });
    });
    const request = new NetworkRequest(); request.setUrl(new Url('https://account.invalid/upload'));
    const form = new Set([new Map<string, string | Blob>([['name', 'Visitor'], ['public_key', new Blob(['public test fixture'])]])]);
    const reply = NetworkAccessManager.getInstance().put(request, form);
    await new Promise<void>(resolve => reply.finished.connect(resolve));
    assert.ok(submitted); assert.equal(submitted.get('name'), 'Visitor');
    const file = submitted.get('public_key'); assert.ok(file instanceof File);
    assert.equal(file.name, 'public_key'); assert.equal(await file.text(), 'public test fixture');
});
