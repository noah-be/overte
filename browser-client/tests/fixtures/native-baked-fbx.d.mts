// SPDX-License-Identifier: Apache-2.0
export interface NativeBakedFbxFixture {buffer:ArrayBuffer;encoded:ArrayBuffer;custom:boolean;positions:Float32Array;uv:Float32Array;uv1?:Float32Array;materialIDs?:Int32Array;originalIndices?:Int32Array}
export function createNativeBakedFbxFixture(custom?:boolean):NativeBakedFbxFixture;
