// SPDX-License-Identifier: Apache-2.0
// Test-only exactly-once recovery of the reviewed style declaration.
import assert from 'node:assert/strict';
export const STYLE_ANCHOR=' property int browserUiEpoch:0;';
export const STYLE_ADDITION=' HifiConstants { id: hifi; }\n';
export function stripBrowserCaptureStyle(value){
 assert.equal(typeof value,'string');
 assert.equal(value.split(STYLE_ADDITION).length,2,'Exactly one reviewed native style declaration');
 assert.equal(value.split(STYLE_ADDITION+STYLE_ANCHOR).length,2,'Reviewed style declaration must retain its exact anchor');
 return value.replace(STYLE_ADDITION+STYLE_ANCHOR,STYLE_ANCHOR);
}
