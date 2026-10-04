// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine native UI discovery only. This probe deliberately performs no entity
// writes and reports no Create/Settings/More functional acceptance.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const client=path.join(repo,'browser-client');
const domain='overte://127.0.0.2:45102';
const base=process.env.OVERTE_LAB_URL||'http://127.0.0.1:8090';
const endpoint=new URL(base);assert(['127.0.0.1','localhost'].includes(endpoint.hostname),'Only the isolated local gateway is admitted for editor discovery');
const systemFirefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const directory=path.join(repo,'build/browser-hub-lab/tablet-editor-routing',systemFirefox?'system-firefox':'chromium');
const report={startedAt:new Date().toISOString(),step:'launch',completed:false,entityMutations:false,sourceHashes:{},screens:[],assertions:[],functionalAcceptance:false};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const sources=['gateway/native-tablet.js','gateway/tablet-capture.qml','tests/integration/tablet-editor-routing.mjs'];
async function hashes(){const result={};for(const name of sources)result[name]=createHash('sha256').update(await readFile(path.join(client,name))).digest('hex');return result;}
let browser,page;
try{
    await mkdir(directory,{recursive:true});report.sourceHashes.start=await hashes();
    const options={headless:process.env.OVERTE_LAB_BROWSER_HEADED!=='1',args:['--use-angle=swiftshader']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=process.env.OVERTE_LAB_CHROMIUM;
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...process.env,LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH};
    browser=systemFirefox?await launchSystemFirefox():await chromium.launch(options);report.browserVersion=browser.version();
    const context=await browser.newContext({viewport:{width:1280,height:900}});page=await context.newPage();if(systemFirefox)await page.bringToFront();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
        const Original=window.WebSocket;window.__editorAudit={frames:[],frame:null,states:[],warnings:[],entityCount:0};
        window.WebSocket=class extends Original{
            constructor(...args){super(...args);this.addEventListener('message',event=>{if(typeof event.data!=='string')return;try{
                const value=JSON.parse(event.data),audit=window.__editorAudit;
                if(value.type==='warning')audit.warnings.push(value.message);
                if(value.type==='entities')audit.entityCount=value.entities.length;
                if(value.type==='tablet'&&value.kind==='frame'){audit.frames.push(value);if(audit.frames.length>8)audit.frames.shift();}
                if(value.type==='tablet'&&value.kind==='state'){audit.states.push({screen:value.screen,visible:value.visible});if(audit.states.length>20)audit.states.shift();}
            }catch{}});}
            send(data){if(typeof data==='string'){try{const value=JSON.parse(data);if(value.type==='tablet'&&value.action==='frameAck'&&value.displayed===true){const audit=window.__editorAudit;const frame=audit.frames.find(item=>item.sequence===value.frameSequence&&item.revision===value.revision);if(frame)audit.frame=frame;}}catch{}}super.send(data);}
        };
    });
    await page.goto(base);await page.locator('#domain').fill(domain);await page.locator('#name').fill('Browser Editor Routing Audit');await page.locator('#join').click();report.step='join';
    await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,undefined,{timeout:90000});
    await page.locator('#tablet').click();await page.waitForFunction(()=>window.__editorAudit.frame?.tabletRect,undefined,{timeout:30000});
    const canvas=page.getByLabel('Native tablet apps and dialogs');
    async function capture(name){
        const frame=await page.evaluate(()=>window.__editorAudit.frame);assert(frame?.tabletRect,'Actual native tablet frame is displayed');
        await writeFile(path.join(directory,name+'-native-ui.png'),Buffer.from(frame.data,'base64'));
        await canvas.screenshot({path:path.join(directory,name+'-browser-ui.png')});
        report.screens.push({name,screen:await page.evaluate(()=>window.__editorAudit.states.at(-1)?.screen),surface:frame.surface,width:frame.width,height:frame.height,tabletRect:frame.tabletRect,pngSha256:createHash('sha256').update(Buffer.from(frame.data,'base64')).digest('hex')});return frame;
    }
    async function newFrame(previous){await page.waitForFunction(previous=>window.__editorAudit.frame.sequence>previous.sequence&&window.__editorAudit.frame.data!==previous.data,previous,{timeout:20000});}
    async function home(){const previous=await page.evaluate(()=>window.__editorAudit.frame);await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForFunction(sequence=>window.__editorAudit.frame.sequence>sequence&&window.__editorAudit.states.at(-1)?.screen==='Home',previous.sequence,{timeout:20000});await delay(1000);}
    async function tapHome(x,y){const frame=await page.evaluate(()=>window.__editorAudit.frame),rect=frame.tabletRect,bounds=await canvas.boundingBox();assert(bounds,'Native tablet canvas is visible');await page.mouse.click(bounds.x+(rect.x+x*rect.width/480)/frame.width*bounds.width,bounds.y+(rect.y+y*rect.height/706)/frame.height*bounds.height);}
    await delay(2000);await capture('home');
    for(const [name,x,y] of [['create',240,460],['settings',100,600],['more',240,600]]){
        report.step=name+' actual native UI';await home();const previous=await page.evaluate(()=>window.__editorAudit.frame);await tapHome(x,y);await newFrame({sequence:previous.sequence,data:previous.data});await delay(2000);await capture(name);
        assert(await page.evaluate(()=>window.__overte.connected),'Opening the installed app preserves the actual domain session');
    }
    assert.equal(errors.length,0,errors.join('\n'));report.assertions.push('Actual native Create, Settings and More screens were captured; no entity mutation or settings effect is claimed');
    await page.getByRole('button',{name:'Close tablet',exact:true}).click();await page.locator('#leave').click();await page.waitForFunction(()=>!window.__overte.connected);report.completed=true;
}catch(error){report.failure=String(error?.message||error);process.exitCode=1;if(page)await page.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});}
finally{await browser?.close();report.sourceHashes.end=await hashes();assert.deepEqual(report.sourceHashes.start,report.sourceHashes.end,'Sources remained frozen during UI discovery');report.finishedAt=new Date().toISOString();const text=JSON.stringify(report,null,2)+'\n';await writeFile(path.join(directory,'tablet-editor-routing-'+report.startedAt.replace(/[:.]/g,'-')+'.json'),text);await writeFile(path.join(directory,'tablet-editor-routing.json'),text);console.log(JSON.stringify(report));}
