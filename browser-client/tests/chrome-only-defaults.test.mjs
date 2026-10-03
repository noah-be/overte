// SPDX-License-Identifier: Apache-2.0
// No browser is launched: these are actual configuration and launch-selection controls.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {execFileSync} from 'node:child_process';
const defaultEnvironment={...process.env};delete defaultEnvironment.OVERTE_BROWSER_CHROME_EXECUTABLE;
const {config,chromeDefaults}=JSON.parse(execFileSync(process.execPath,['--input-type=module','-e',"import config from './playwright.config.ts';import {googleChromeLaunchOptions} from './tests/google-chrome-selection.mjs';console.log(JSON.stringify({config,chromeDefaults:googleChromeLaunchOptions()}))"],{cwd:new URL('..',import.meta.url),env:defaultEnvironment,encoding:'utf8',timeout:10000}));

test('default actual-browser project selects branded Google Chrome and keeps renderer gates',()=>{
 assert.equal(config.projects.length,1);assert.equal(config.projects[0].name,'google-chrome');assert.equal(config.projects[0].use.channel,'chrome');assert.equal(config.timeout,45000);assert.equal(config.expect.timeout,10000);assert.equal(config.fullyParallel,true);assert.equal(config.testMatch,'*.browser.spec.ts');assert.equal(config.use.trace,'retain-on-failure');assert.deepEqual(config.projects[0].use.launchOptions.args,['--use-angle=swiftshader']);
});
test('default actual native journey uses Chrome channel without stale Chromium overrides',async()=>{
 const source=await readFile(new URL('./integration/real-session.mjs',import.meta.url),'utf8');const start=source.indexOf('async function startBrowser() {'),end=source.indexOf('\nasync function screenshot',start);assert(start>=0&&end>start);
 let calls=0;const context={googleChromeLaunchOptions:()=>chromeDefaults,process:{env:{LD_LIBRARY_PATH:'legacy',OVERTE_LAB_CHROMIUM:'/legacy/chromium',OVERTE_LAB_CHROMIUM_LIBRARY_PATH:'/legacy/lib',OVERTE_LAB_BROWSER_DISPLAY:':owned'}},browserKind:'chrome',isChromium:true,browserPulse:'owned',evidenceDirectory:'/owned',repo:'/owned',path:{resolve:(...values)=>values.join('/')},chromium:{launch:async options=>{calls++;assert.equal(options.channel,'chrome');assert.equal(options.executablePath,undefined);assert(!('LD_LIBRARY_PATH'in options.env));assert(options.args.includes('--use-fake-device-for-media-stream'));assert(options.args.includes('--use-fake-ui-for-media-stream'));assert.equal(JSON.stringify(options.ignoreDefaultArgs),JSON.stringify(['--mute-audio']));return options;}},firefox:{launch(){throw Error('No default Firefox launch');}},launchSystemFirefox(){throw Error('No default Firefox launch');}};
 vm.createContext(context);vm.runInContext(source.slice(start,end)+'\nresult=startBrowser();',context);await context.result;assert.equal(calls,1);
});
test('automated browser workflow and pixel wrappers launch Google Chrome only',async()=>{
 const workflow=await readFile(new URL('../../.github/workflows/browser-client.yml',import.meta.url),'utf8');assert(!/firefox/i.test(workflow));assert.equal(workflow.split('npx playwright install --with-deps chrome').length,3);assert(workflow.includes('npm run test:browser -- --headed'));assert(workflow.includes('--browser chrome'));
 for(const name of ['run-embedded-journey.sh','run-native-ignored-fbx-journey.sh']){const source=await readFile(new URL('../lab/'+name,import.meta.url),'utf8');assert(source.includes('for engine in chrome; do'));assert(!source.includes('firefox'));}
});
test('default core evidence curation writes only Chrome and keeps completed journey controls',async()=>{
 const {mkdtemp,readdir,rm,readFile:read}=await import('node:fs/promises');const {tmpdir}=await import('node:os');const {join}=await import('node:path');const {fileURLToPath}=await import('node:url');const {execFile}=await import('node:child_process');const {promisify}=await import('node:util');const exec=promisify(execFile);
 const directory=await mkdtemp(join(tmpdir(),'overte-chrome-curation-cpu-'));const curator=fileURLToPath(new URL('../lab/curate-core-journey.py',import.meta.url));
 try{
  await exec('python3',['-c',"import importlib.util,json,pathlib,sys; spec=importlib.util.spec_from_file_location('curator',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); p=pathlib.Path(sys.argv[2]); p.mkdir(); d={'completed':True,'syntheticMicrophone':True,'durationSeconds':0,'browserVersion':'154.0.8037.97','checkpoints':[{'name':name} for name in m.CHECKPOINTS]}; (p/'real-session-chrome.json').write_text(json.dumps(d))",curator,join(directory,'input')],{timeout:10000});
  await exec('python3',[curator,'--input',join(directory,'input'),'--output',join(directory,'output')],{timeout:10000});assert.deepEqual(await readdir(join(directory,'output')),['core-journey-chrome.json']);const proof=JSON.parse(await read(join(directory,'output/core-journey-chrome.json'),'utf8'));assert.equal(proof.browser,'chrome');assert.equal(proof.completed,true);assert.equal(proof.checkpoints.length,18);assert.equal(proof.browserVersion,'154.0.8037.97');
 }finally{await rm(directory,{recursive:true,force:true});}
});
