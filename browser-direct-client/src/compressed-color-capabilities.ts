// SPDX-License-Identifier: Apache-2.0
import type { CompressionCapabilities } from './native-compressed-color';
interface CurrentRendererCapabilities {
  readonly capabilities: { readonly maxTextureSize: number };
  readonly extensions: { has(name: string): boolean };
}
/** Read Three's current renderer-owned cache, not another WebGL query or a
 * browser-global snapshot. Context restoration replaces both public objects. */
export function currentCompressedColorCapabilities(renderer: CurrentRendererCapabilities): CompressionCapabilities {
  return {
    s3tc: renderer.extensions.has('WEBGL_compressed_texture_s3tc'),
    s3tcSRGB: renderer.extensions.has('WEBGL_compressed_texture_s3tc_srgb'),
    maximumTextureSize: renderer.capabilities.maxTextureSize,
  };
}
