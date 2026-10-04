// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import{execFileSync}from'node:child_process';import{fileURLToPath}from'node:url';
test('actual builder explicit CLI selection preserves system tests and pinned CI route',()=>{
 execFileSync('python3',[fileURLToPath(new URL('../native-input/web-editor/test-cli.py',import.meta.url))],{timeout:5000,stdio:'pipe'});
});
