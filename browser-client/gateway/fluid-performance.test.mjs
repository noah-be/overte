// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {assessFluidPerformance} from '../shared/fluid-performance.mjs';
const smooth = {fps:42,p95FrameMs:33.4,maximumFrameMs:83,samples:240};
test('public-world fluid acceptance distinguishes successful rendering from measured fluidness and stalls',()=>{
    assert.equal(assessFluidPerformance([smooth,smooth]).passed,true);
    for (const defect of [{fps:20},{p95FrameMs:109,maximumFrameMs:200},{maximumFrameMs:1450},{samples:20},{fps:NaN}]) {
        assert.equal(assessFluidPerformance([smooth,{...smooth,...defect}]).passed,false);
    }
    assert.equal(assessFluidPerformance([smooth]).passed,false);
    assert.equal(assessFluidPerformance(undefined).passed,false);
});
