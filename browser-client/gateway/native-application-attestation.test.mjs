// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
test('descriptor-bound native application-key source/header/module attestation refuses mutations and aliases',()=>{
  const file=fileURLToPath(new URL('../native-input/web-editor/test-application-key-attestation.py',import.meta.url));
  const result=spawnSync('python3',[file],{encoding:'utf8',timeout:10000,maxBuffer:65536});
  assert.equal(result.error,undefined);
  assert.equal(result.status,0,'Actual CPU attestation suite must pass');
  assert.match(result.stderr,/Ran 9 tests/);
  assert.match(result.stderr,/\bOK\b/);
});
