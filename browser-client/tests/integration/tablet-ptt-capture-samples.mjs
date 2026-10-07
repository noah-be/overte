// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Test-only capture bound: resample first, then count actual output samples.
import assert from 'node:assert/strict';
export function exactPttCaptureFilter(seconds){
 assert(Number.isSafeInteger(seconds)&&seconds>=1&&seconds<=5,'Owned capture duration refused');
 return 'aresample=48000,atrim=end_sample='+seconds*48000;
}
