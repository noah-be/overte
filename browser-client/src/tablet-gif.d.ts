// SPDX-License-Identifier: Apache-2.0
declare module 'gifenc' {
    export function GIFEncoder():{writeFrame(pixels:Uint8Array,width:number,height:number,options:{palette:number[][];delay:number;repeat?:number}):void;finish():void;bytes():Uint8Array};
    export function quantize(pixels:Uint8ClampedArray,maxColors:number):number[][];
    export function applyPalette(pixels:Uint8ClampedArray,palette:number[][]):Uint8Array;
}
