// SPDX-License-Identifier: Apache-2.0
// Actual public world inventory, always muted; private names are never curated.
import { chromium } from '@playwright/test';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const output=path.join(repo,'build/browser-hub-lab/batch-inventory');
const report={startedAt:new Date().toISOString(),completed:false,place:'overte_hub',microphoneRequested:false,worldInteractionsSent:0};
let browser,page;
try {
  await mkdir(output,{recursive:true});
  const env={...process.env,PULSE_SERVER:`unix:${repo}/build/browser-hub-lab/hub/pulse.socket`};
  if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)env.LD_LIBRARY_PATH=process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH;
  if(process.env.OVERTE_LAB_BROWSER_DISPLAY)env.DISPLAY=process.env.OVERTE_LAB_BROWSER_DISPLAY;
  browser=await chromium.launch({headless:!process.env.OVERTE_LAB_BROWSER_DISPLAY,args:['--disable-dev-shm-usage','--mute-audio'],env,...(process.env.OVERTE_LAB_CHROMIUM?{executablePath:process.env.OVERTE_LAB_CHROMIUM}:{})});
  report.browserVersion=browser.version();page=await browser.newPage({viewport:{width:1280,height:800}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8095');
  await page.locator('#domain').fill('overte://overte_hub');await page.locator('#name').fill('Browser compatibility observer');await page.locator('#join').click();
  await page.waitForFunction(()=>window.__overte?.connected||document.querySelector('#notice[data-kind="error"]'),null,{timeout:60000});
  if(!await page.evaluate(()=>window.__overte.connected))throw Error(await page.locator('#notice').textContent());
  await page.waitForFunction(()=>window.__overte.entityCount>20&&window.__overte.performance.loadingModels===0&&window.__overte.performance.queuedModels===0&&window.__overte.performance.compilingGraphics===0,null,{timeout:90000});
  report.inventory=await page.evaluate(()=>window.__overte.renderInventory);
  report.performance=await page.evaluate(()=>window.__overte.performance);
  report.summary={models:report.inventory.length,meshes:0,groups:0,materials:0,triangles:0,skins:0,morphs:0,eligibleDrawCalls:0,savedDrawCalls:0,actualSavedDrawCalls:0,generatedBytes:0};
  for(const model of report.inventory){report.summary.actualSavedDrawCalls+=model.batchedDrawCallsSaved||0;for(const key of ['meshes','groups','materials','triangles','skins','morphs'])report.summary[key]+=model[key];const candidate=model.batchCandidate;if(candidate){report.summary.eligibleDrawCalls+=candidate.sourceDrawCalls;report.summary.savedDrawCalls+=candidate.savedDrawCalls;report.summary.generatedBytes+=candidate.generatedBytes;}}
  report.pageErrors=errors;report.completed=true;
  await page.locator('#leave').click();
}catch(error){report.error=error.message;process.exitCode=1;}
finally {
  await browser?.close();report.finishedAt=new Date().toISOString();
  report.sourceSHA256={};for(const file of ['browser-client/dist/index.html','browser-client/src/static-model-batch.ts','browser-client/src/world.ts'])report.sourceSHA256[file]=createHash('sha256').update(await readFile(path.join(repo,file))).digest('hex');
  await writeFile(path.join(output,'inventory-private.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({startedAt:report.startedAt,finishedAt:report.finishedAt,completed:report.completed,error:report.error,summary:report.summary,performance:report.performance,report:path.relative(repo,path.join(output,'inventory-private.json'))}));
}
