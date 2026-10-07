// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import AccountManager from '../src/protocol/vircadia/domain/networking/AccountManager';
import ContextManager from '../src/protocol/vircadia/domain/shared/ContextManager';
import Url from '../src/protocol/vircadia/domain/shared/Url';

test('anonymous/refused accounts cannot generate or upload directory keys; explicit authenticated accounts retain the path', async context => {
    let keyGenerations = 0;
    context.mock.method(crypto.subtle, 'generateKey', async () => {
        keyGenerations++;
        throw new Error('Controlled key-generation failure; no keys or requests are created.');
    });
    const account = new AccountManager(ContextManager.createContext());
    account.generateNewUserKeypair();
    account.setAuthURL(new Url('https://account.example.invalid/'));
    account.generateNewUserKeypair();
    account.getAccountInfo().setUsername('fixture-user');
    account.generateNewUserKeypair();
    await Promise.resolve();
    assert.equal(keyGenerations, 0, 'a username and configured URL without login cannot initiate a write');
    account.getAccountInfo().setAccessTokenFromJSON({ access_token: 'fixture-token-not-a-real-credential',
        token_type: 'Bearer', expires_in: 3600 });
    assert.equal(account.isLoggedIn(), true);
    account.getAccountInfo().setUsername('');
    account.generateNewUserKeypair();
    assert.equal(keyGenerations, 0, 'an anonymous account still has no username to sign/upload');
    account.getAccountInfo().setUsername('fixture-user');
    account.generateNewUserKeypair();
    await Promise.resolve();
    assert.equal(keyGenerations, 1, 'the actual authenticated account path remains available');
});
