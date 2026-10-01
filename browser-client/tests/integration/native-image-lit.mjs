// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// The emissive baseline keeps its absolute PNG oracle. Lit images instead retain
// source detail plus an additional strict actual native/browser RGB comparison:
// incident light is not substituted with the original unlit source colors.
import {imagePixelComparison} from './native-image-pixels.mjs';
export function imageLightingCohort(value){
 if(value===undefined||value==='unlit')return Object.freeze({name:'unlit',emissive:true});
 if(value==='lit')return Object.freeze({name:'lit',emissive:false});
 throw Error('OVERTE_IMAGE_LIGHTING must be exactly unlit or lit');
}
export function assertLitImagePixels(native,browser,nativeSource,browserSource){
 const nativeDetail=imagePixelComparison(native,nativeSource),browserDetail=imagePixelComparison(browser,browserSource);
 for(const detail of [nativeDetail,browserDetail]){
  if(detail.correlation<.9)throw Error('Actual lit Image detail/UV orientation must match the audited source');
  if(detail.maskMismatch>.03)throw Error('Actual lit Image holes must match the audited source');
 }
 const crossEngine=imagePixelComparison(native,browser);
 if(crossEngine.rgbMAE>10)throw Error('Actual lit native/browser Image lighting colors exceed the fixed ten-level RGB-error bound');
 if(crossEngine.correlation<.9)throw Error('Actual lit native/browser Image detail must correlate');
 if(crossEngine.maskMismatch>.03)throw Error('Actual lit native/browser Image holes must agree');
 return {nativeDetail,browserDetail,crossEngine};
}
