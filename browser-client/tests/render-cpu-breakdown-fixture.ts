// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {RenderCpuBreakdown} from '../src/render-cpu-breakdown';
export * as THREE from 'three';
export {BrowserWorld} from '../src/world';
export {RenderCpuBreakdown};

/** Fixture census accounting only: these synthetic spans are not host CPU time. */
export function bindAttributionFixtureClock(world:{abort:AbortController;renderCpuTiming:RenderCpuBreakdown},enabled:boolean){
 if(!(world.renderCpuTiming instanceof RenderCpuBreakdown)||!(world.abort instanceof AbortController)||typeof enabled!=='boolean'||world.renderCpuTiming.snapshot().active)throw Error('Invalid owned attribution fixture observer');
 let ticks=0;
 const now=()=>{if(ticks===65536)throw Error('Attribution fixture clock capacity exceeded');return ++ticks/1024;};
 world.renderCpuTiming.dispose();
 world.renderCpuTiming=new RenderCpuBreakdown(world.abort.signal,{dispatchAttribution:enabled,now});
 return 'synthetic-fixture-not-host-CPU' as const;
}
