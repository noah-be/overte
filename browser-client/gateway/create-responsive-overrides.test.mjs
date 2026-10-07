// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,mkdtemp,writeFile,mkdir,symlink,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {responsiveCreateHTML,buildResponsiveCreateHTML,loadBrowserCreatePackage,RESPONSIVE_CREATE_CSS} from './create-responsive-overrides.mjs';

const native=await readFile(new URL('../../scripts/system/create/entityProperties/html/entityProperties.html',import.meta.url),'utf8');
test('only the pinned authentic Properties HTML receives narrow responsive CSS; every original byte remains',()=>{
 const patched=responsiveCreateHTML(native);
 const inserted='        <style id="browser-create-responsive-layout">'+RESPONSIVE_CREATE_CSS+'</style>\n';
 assert.equal(patched.replace(inserted,''),native);
 assert.equal(patched.split(inserted).length,2);
 assert(!RESPONSIVE_CREATE_CSS.includes('display:none'));assert(!RESPONSIVE_CREATE_CSS.includes('pointer-events'));
 for(const invalid of [native+' ',native.replace('loaded();','changed();'),''])assert.throws(()=>responsiveCreateHTML(invalid),/Unsupported/);
 assert.throws(()=>buildResponsiveCreateHTML({}),/Unsupported/);
});
test('installed-source paths refuse remote files and never follow a substituted local source symlink',async()=>{
 for(const address of ['https://example.test/defaultScripts.js','file://other-host/defaultScripts.js','file:///tmp/other.js'])await assert.rejects(loadBrowserCreatePackage(address),/Invalid/);
 const directory=await mkdtemp(join(tmpdir(),'create-layout-'));
 try{const target=join(directory,'system/create/entityProperties/html/entityProperties.html');await mkdir(join(directory,'system/create/entityProperties/html'),{recursive:true});
 const outside=join(directory,'outside.html');await writeFile(outside,native);await symlink(outside,target);
 await assert.rejects(loadBrowserCreatePackage(pathToFileURL(join(directory,'defaultScripts.js')).href));
 }finally{await rm(directory,{recursive:true,force:true});}
});
