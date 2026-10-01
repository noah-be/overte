// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Offline audit CLI. Validation is shared with the isolated compressed color prototype.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {inspectNativeKtx} from '../shared/native-ktx.mjs';
export {inspectNativeKtx} from '../shared/native-ktx.mjs';
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1])){
 const root=process.env.OVERTE_KTX_AUDIT_ROOT||path.resolve('..','build/browser-hub-lab/hub'),report={scope:'Audit only: actual saved public Hub KTX bytes, no renderer or runtime changes',assets:[]};
 for(const name of ['shrub-jungle-leafy-1a','shrub-bluepops-1a','shrub-noodle-1b','tree-palm-sago','Tree-Royal-Poinciana-1']){
  const bytes=await readFile(path.join(root,name+'.ktx')),result=inspectNativeKtx(bytes);
  report.assets.push({asset:name,sha256:createHash('sha256').update(bytes).digest('hex'),fileBytes:bytes.length,...result,mipmaps:result.mipmaps.map(({data,...rest})=>rest)});
 }
 console.log(JSON.stringify(report,null,2));
}
