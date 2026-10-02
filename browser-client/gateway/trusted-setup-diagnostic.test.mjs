// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {preparationDiagnostics,safePreparationDiagnostic,safeTrustedSetupFailure}from './preparation-diagnostics.mjs';
const marker=value=>'OVERTE_NET_TRUSTED_FAILURE='+JSON.stringify(value)+'\nTrusted network setup refused.\n';
const fixed={version:1,phase:'route-install-ack',errnoObserved:1};
test('fixed C marker survives fragmented observed pipes without changing original preparation failure or counters',()=>{
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED'),text=marker(fixed);for(let i=0;i<text.length;i+=3)d.observe(Buffer.from(text.slice(i,i+3)));const out=d.snapshot(78,null);assert.deepEqual(out.trustedSetupFailure,fixed);assert.equal(out.phase,'native-started');assert.equal(out.category,'unclassified-child-exit');assert.equal(out.observedBytes,Buffer.byteLength(text));assert.equal(out.exitCode,78);assert.equal(out.truncated,false);assert(Object.isFrozen(out.trustedSetupFailure));assert.deepEqual(safePreparationDiagnostic(out),out);
});
test('fixed zero and largest kernel errno observations remain data rather than admission or cause',()=>{
 for(const errnoObserved of[0,4095]){const record={...fixed,errnoObserved};assert.deepEqual(safeTrustedSetupFailure(record),record);}for(const errnoObserved of[-1,4096,Infinity,NaN,true,'1',1.5,null])assert.equal(safeTrustedSetupFailure({...fixed,errnoObserved}),null);
});
test('unknown extra fields, labels/version/types and prototype-like names refuse without selector disclosure',()=>{
 for(const patch of[{version:2},{version:true},{phase:'private-path/token'},{phase:'__proto__'},{phase:null},{raw:'private-path/token'},{descriptor:3}]){const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from(marker({...fixed,...patch})));const out=d.snapshot(78,null);assert.equal(out.trustedSetupFailure,undefined);assert.equal(JSON.stringify(out).includes('private-path/token'),false);assert.equal(safePreparationDiagnostic({...out,trustedSetupFailure:{...fixed,...patch}}),null);}
});
test('exact wire rejects duplicate keys, aliases, reordered/escaped records and multiple ambiguous markers',()=>{
 for(const payload of['{"version":1,"version":1,"phase":"route-install-ack","errnoObserved":1}','{"phase":"route-install-ack","version":1,"errnoObserved":1}','{"version":1,"phase":"route-install-ack","errnoObserved":01}','{"version":1,"phase":"route-install-ack","errnoObserved":1e0}','{"version":1,"phase":"route-install-ack","errnoObserved":true}','{"version":1,"phase":"route-install-ack","errnoObserved":-0}','{"version":1,"phase":"route\\u002dinstall-ack","errnoObserved":1}']){const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from('OVERTE_NET_TRUSTED_FAILURE='+payload+'\n'));assert.equal(d.snapshot(78,null).trustedSetupFailure,undefined);}
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from(marker(fixed)+marker({...fixed,phase:'route-readback'})));assert.equal(d.snapshot(78,null).trustedSetupFailure,undefined);
});
test('bounded tail truncation remains explicit; known marker does not reflect any earlier raw data',()=>{
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from('private-path/token'.repeat(2000)+'\n'));d.observe(Buffer.from(marker(fixed)));const out=d.snapshot(78,null);assert.equal(out.truncated,true);assert.deepEqual(out.trustedSetupFailure,fixed);assert.equal(JSON.stringify(out).includes('private-path/token'),false);
});
test('plain nested diagnostic is reconstructed and frozen without retaining its mutable source',()=>{
 const d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');const base=d.snapshot(78,null),input={...fixed};const out=safePreparationDiagnostic({...base,trustedSetupFailure:input,ignoredRaw:'private-path/token'});input.errnoObserved=13;assert.equal(out.trustedSetupFailure.errnoObserved,1);assert(Object.isFrozen(out.trustedSetupFailure));assert.equal(JSON.stringify(out).includes('private-path/token'),false);
});

test('fixed interpreter/import/alias subphases preserve legacy Python label and original failure without reflecting aliases',()=>{
 for(const phase of ['python-image', 'python-image-open','python-image-hash','python-import-roots','python-import-root-open','python-import-root-stat','python-import-scan','python-import-alias-resolve','python-import-alias-target']){
  const value={version:1,phase,errnoObserved:13},d=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');d.observe(Buffer.from(marker(value)));const out=d.snapshot(78,null);assert.deepEqual(out.trustedSetupFailure,value);assert.equal(out.exitCode,78);assert.equal(out.category,'unclassified-child-exit');assert.deepEqual(safePreparationDiagnostic(out),out);
 }
 for(const phase of ['python-import-/private/alias','python-image-open:fd=3','python-import-alias-target-secret'])assert.equal(safeTrustedSetupFailure({...fixed,phase}),null);
});
