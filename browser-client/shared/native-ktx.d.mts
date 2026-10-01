// SPDX-License-Identifier: Apache-2.0
export interface NativeKtx {
 width: number; height: number; mipmapCount: number; completeMipChain: boolean; glInternalFormat: number;
 format: {name: string; threeFormat: number; blockBytes: number; srgb: boolean; alpha: boolean};
 nativeUsage: {originalSize?:{width:number;height:number};version: number; flags: number; color: boolean; normal: boolean; classification: 'opaque'|'mask'|'blend'};
 orientation: 'S=r,T=u'|'S=r,T=d'|null; payloadBytes: number;
 mipmaps: Array<{width: number; height: number; byteLength: number; data: Uint8Array}>;
}
export function inspectNativeKtx(input: ArrayBuffer|ArrayBufferView): NativeKtx;
