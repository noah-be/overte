// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Execute unchanged registered assertions; adaptation is limited to registration/imports.
import {expect} from '@playwright/test';
import {transformWithOxc} from 'vite';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {replacementMaterialFbx,replacementRGBA} from '../fixtures/replacement-material-fbx.ts';
export const cloneVariants=Object.freeze(['opaque','rgb','skin','blend','mask','foreign']);
export async function registeredCloneBodies(file){
 const source=await readFile(file,'utf8');
 const imports=["import {test,expect} from '@playwright/test';","import {replacementMaterialFbx,replacementRGBA} from './fixtures/replacement-material-fbx';"];
 let adapted=source;
 for(const marker of imports){assert.equal(adapted.split(marker).length,2,'Exact reviewed registration/import marker required');adapted=adapted.replace(marker,marker===imports[0]?'const test=injectedTest,expect=injectedExpect;':'const replacementMaterialFbx=injectedFbx,replacementRGBA=injectedRGBA;');}
 const compiled=await transformWithOxc(adapted,file),registered=[];
 vm.runInNewContext(compiled.code,{Buffer,URL,injectedExpect:expect,injectedFbx:replacementMaterialFbx,injectedRGBA:replacementRGBA,
  injectedTest:(name,callback)=>{const variant=cloneVariants[registered.length];assert(variant,'Only six exact tests are admitted');assert.equal(name,`Actual FBX/World ordered replacement clone reuse preserves strict ${variant} pixels and teardown`);assert.equal(typeof callback,'function');registered.push(Object.freeze({variant,name,callback}));}}, {timeout:1000});
 assert.equal(registered.length,6);return Object.freeze(registered);
}
