// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {readFile,mkdtemp,mkdir,symlink,writeFile,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {BrowserCaptureTarget,type CaptureBinding} from './browser-capture-target.ts';
test('actual Target old owner-first branch loses deliberate restore refusal; corrected branch preserves terminal reason',async()=>{
 const source=await readFile(new URL('./browser-capture-target.ts',import.meta.url),'utf8');
 const after="     if(stopped||!current()){if(this.owned(b))b.stop();return 'cancelled';}\n     // A failed exact restore deliberately ends this binding. Preserve that\n     // terminal refusal while still giving external cancellation precedence.\n     if(fresh==='rollback-refused')return fresh;\n     if(!this.owned(b))return 'cancelled';\n";
 const before="     if(stopped||!current()||!this.owned(b)){if(this.owned(b))b.stop();return 'cancelled';}\n";
 assert.equal(source.split(after).length,2);const scratch=await mkdtemp(join(tmpdir(),'overte-capture-reason-control-'));
 try{await mkdir(join(scratch,'src'));await symlink(fileURLToPath(new URL('../shared',import.meta.url)),join(scratch,'shared'),'dir');const file=join(scratch,'src','target.ts');await writeFile(file,source.replace(after,before),{mode:0o600});const old=await import(pathToFileURL(file).href);
  for(const[Target,expected]of [[old.BrowserCaptureTarget,'cancelled'],[BrowserCaptureTarget,'rollback-refused']]as const){let valid=true,stops=0;
   const track={readyState:'live',getSettings:()=>({echoCancellation:true,noiseSuppression:true,autoGainControl:true}),getCapabilities:()=>({echoCancellation:[true,false],noiseSuppression:[true,false],autoGainControl:[true,false]}),getConstraints:()=>({})};
   const b:CaptureBinding={track:track as unknown as MediaStreamTrack,gain:{gain:{value:1}}as GainNode,current:()=>valid,inhibit(){},stop(){valid=false;stops++;track.readyState='ended';},committed(){assert.fail('A refusal cannot commit');},async restartProcessing(){b.stop();return 'rollback-refused';}};
   const target=new Target(()=>valid?b:undefined);const r=await target.apply({field:'echoCancellation',value:false},()=>true);assert.equal(r.reason,expected);assert.equal(r.accepted,false);assert.equal(r.state.active,false);assert.equal(stops,1);
  }
 }finally{await rm(scratch,{recursive:true,force:true});}
});
