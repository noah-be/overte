// SPDX-License-Identifier: Apache-2.0
import { DoubleSide, Material } from 'three';
import { getNativeAlphaOptions, hasNativeAlphaShader, type MappedMaterial } from '../src/native-alpha-material';
/** Exact authored fixture contract. Native MASK owns its registered fragment
 * hook; BLEND intentionally retains Three's sampled-alpha × scalar-opacity
 * callbacks. Requiring a BLEND hook would fail even before shader preparation. */
export function warmupNativeAlphaContract(mask:MappedMaterial,blend:MappedMaterial):boolean {
  const maskOptions=getNativeAlphaOptions(mask),blendOptions=getNativeAlphaOptions(blend);
  return hasNativeAlphaShader(mask) && !hasNativeAlphaShader(blend) &&
    blend.onBeforeCompile===Material.prototype.onBeforeCompile && blend.customProgramCacheKey===Material.prototype.customProgramCacheKey &&
    maskOptions?.useAlpha===true && maskOptions.mode==='OPACITY_MAP_MASK' && maskOptions.cutoff===.375 &&
    blendOptions?.useAlpha===true && blendOptions.mode==='OPACITY_MAP_BLEND' && blendOptions.cutoff===.5 &&
    Boolean(mask.map&&blend.map) && mask.alphaMap===null && blend.alphaMap===null &&
    mask.opacity===1 && mask.alphaTest===.375 && mask.transparent===false && mask.depthWrite===true &&
    blend.opacity===.55 && blend.alphaTest===0 && blend.transparent===true && blend.depthWrite===false &&
    mask.side===DoubleSide && blend.side===DoubleSide && mask.forceSinglePass===true && blend.forceSinglePass===true;
}
