// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Readback readiness only. Original source/native/browser pixel thresholds stay unchanged.
import {imagePixelComparison} from './native-image-pixels.mjs';
const MIN_STABLE_CAPTURES=3,MAX_CAPTURES=8;
function identity(d){
    if(!d||d.resourceState!==3||!Number.isSafeInteger(d.renderFrames)||!Number.isSafeInteger(d.finishedFrameBaseline)||
        d.finishedFrameBaseline<0||d.renderFrames-d.finishedFrameBaseline<3||!['opaque-original','opaque-compressed','mask-original','mask-compressed'].includes(d.current)||
        ![0,1].includes(d.renderMethod)||!d.camera||d.camera.mode!=='independent'||!d.antialiasing||![3,16].includes(d.antialiasing.minimumSnapshotFrames))throw Error('Native convergence requires actual FINISHED resource, camera and frame/AA readiness');
    const c=d.camera;for(const value of [c.position?.x,c.position?.y,c.position?.z,c.orientation?.x,c.orientation?.y,c.orientation?.z,c.orientation?.w,c.fieldOfView,c.aspectRatio])if(!Number.isFinite(value))throw Error('Native convergence camera readback must be finite');
    return JSON.stringify([d.current,d.renderMethod,d.finishedFrameBaseline,c.position,c.orientation,c.fieldOfView,c.aspectRatio,d.antialiasing]);
}
/** Bounded actual captures, never a time-based substitute for native frames. */
export class NativeImageConvergence {
    #identity=null;#lastFrame=null;#samples=[];#attempts=0;
    push(diagnostic,pixels){
        if(this.#attempts>=MAX_CAPTURES)throw Error('Native Image pixels did not converge within eight bounded captures');
        if(!pixels||!Number.isSafeInteger(pixels.width)||!Number.isSafeInteger(pixels.height)||pixels.width<1||pixels.height<1||pixels.width*pixels.height>4*1024*1024||!pixels.crop||!['x','y','width','height'].every(key=>Number.isFinite(pixels.crop[key]))||pixels.crop.x<0||pixels.crop.y<0||pixels.crop.width<=0||pixels.crop.height<=0||pixels.crop.x+pixels.crop.width>pixels.width||pixels.crop.y+pixels.crop.height>pixels.height)throw Error('Native convergence requires bounded actual screenshot/crop geometry');
        const signature=identity(diagnostic)+JSON.stringify([pixels.width,pixels.height,pixels.crop]);imagePixelComparison(pixels,pixels);
        if(signature!==this.#identity){this.#identity=signature;this.#lastFrame=null;this.#samples=[];}
        if(this.#lastFrame!==null&&diagnostic.renderFrames-this.#lastFrame<diagnostic.antialiasing.minimumSnapshotFrames)throw Error('Native convergence captures must be separated by actual post-FINISHED frames');
        this.#lastFrame=diagnostic.renderFrames;this.#attempts++;
        const copied={rgb:pixels.rgb.slice(),mask:pixels.mask.slice()};
        const deltas=this.#samples.map(prior=>imagePixelComparison(prior,copied));
        // Stricter stability criteria than the independent unchanged acceptance
        // oracle. Pairwise matching prevents small accumulating frame drift.
        const stable=deltas.every(delta=>delta.rgbMAE<=0.5&&delta.maskMismatch<=0.0025);
        if(!stable)this.#samples=[];
        this.#samples.push(copied);
        if(this.#samples.length>MIN_STABLE_CAPTURES)this.#samples.shift();
        return {ready:this.#samples.length>=MIN_STABLE_CAPTURES,captures:this.#attempts,stableCaptures:this.#samples.length,
            renderFrames:diagnostic.renderFrames,finishedFrameBaseline:diagnostic.finishedFrameBaseline,minimumSnapshotFrames:diagnostic.antialiasing.minimumSnapshotFrames,
            pairwiseDeltas:deltas.map(({rgbMAE,maskMismatch})=>({rgbMAE,maskMismatch}))};
    }
}
