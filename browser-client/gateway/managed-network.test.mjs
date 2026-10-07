// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { managedUDPDomain } from './validation.mjs';

test('managed network scope uses only validated loopback destination and exact operator UDP ports', () => {
    assert.deepEqual(managedUDPDomain('overte://127.0.0.2:45102', '45102,45200,45201'),
        { address: '127.0.0.2', ports: [45102, 45200, 45201] });
    assert.deepEqual(managedUDPDomain('overte://127.0.0.3', '40102'), { address: '127.0.0.3', ports: [40102] });
    for (const address of ['127.0.0.1', '192.168.0.2', '1.1.1.1', 'localhost', '[::1]']) {
        assert.throws(() => managedUDPDomain(`overte://${address}:45102`, '45102'), /dedicated loopback/);
    }
    for (const ports of [undefined, '', '45200', '45102,45102', '0,45102', '65536,45102', '45102,1e3', '45102, 45200']) {
        assert.throws(() => managedUDPDomain('overte://127.0.0.2:45102', ports), /UDP.*ports/);
    }
});
