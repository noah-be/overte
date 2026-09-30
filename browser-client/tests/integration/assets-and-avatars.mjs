// SPDX-License-Identifier: Apache-2.0
// Focused actual-domain proof: binary ATP texture fidelity and rendered native peer.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const directory=path.join(repo,'build/browser-lab/evidence');
const report={startedAt:new Date().toISOString(),completed:false};
const sha=buffer=>createHash('sha256').update(buffer).digest('hex');
let browser;
try {
    await mkdir(directory,{recursive:true});
    report.sourceSHA256={};
    const files=['browser-client/gateway/server.mjs','browser-client/gateway/native-bridge.js',
        'browser-client/gateway/validation.mjs','browser-client/gateway/permission-policy.mjs','browser-client/gateway/process-lifecycle.mjs',
        'browser-client/dist/index.html','browser-client/tests/integration/assets-and-avatars.mjs'];
    for(const asset of await readdir(path.join(repo,'browser-client/dist/assets')))files.push(`browser-client/dist/assets/${asset}`);
    for(const file of files)report.sourceSHA256[file]=sha(await readFile(path.join(repo,file)));
    browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--disable-dev-shm-usage'],
        env:{...process.env,PULSE_SERVER:`unix:${repo}/build/browser-lab/runtime/browser-pulse.sock`}});
    report.browserVersion=browser.version();
    const page=await browser.newPage({viewport:{width:1280,height:800}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
        const Original=window.WebSocket;
        window.__assetProof={sessionId:null,avatars:[]};
        window.WebSocket=class extends Original {
            constructor(...args){super(...args);this.addEventListener('message',event=>{
                if(typeof event.data!=='string')return;
                try{const message=JSON.parse(event.data);if(message.sessionId)window.__assetProof.sessionId=message.sessionId;
                    if(message.type==='avatars')window.__assetProof.avatars=message.avatars;
                }catch{}
            });}
        };
    });
    const textureResponses=[];
    page.on('response',response=>{const raw=new URL(response.url()).searchParams.get('url');
        if(raw==='atp:/browser-lab/checker.png')textureResponses.push({status:response.status(),url:raw});});
    await page.goto(process.env.OVERTE_LAB_URL||'http://127.0.0.1:8090');
    await page.locator('#domain').fill('overte://127.0.0.2:45102');
    await page.locator('#name').fill('Browser asset and avatar proof');
    await page.locator('#join').click();
    await page.waitForFunction(()=>window.__overte?.connected&&window.__overte.entityCount>=7,null,{timeout:60000});
    await page.waitForFunction(()=>document.querySelector('#events').textContent.includes('Loaded Browser Lab ATP Textured Model'),null,{timeout:30000});
    assert(textureResponses.length>0,'The actual glTF renderer downloaded its separate ATP PNG dependency');
    const sessionId=await page.evaluate(()=>window.__assetProof.sessionId);
    const response=await page.request.get(`http://127.0.0.1:8090/api/assets/${sessionId}?url=${encodeURIComponent('atp:/browser-lab/checker.png')}`);
    assert.equal(response.status(),200,'Owned real session can download its actual binary ATP image');
    const received=await response.body(),expected=await readFile(path.join(repo,'browser-client/lab/checker.png'));
    assert.equal(sha(received),sha(expected),'Native asset transport preserves all binary PNG bytes');
    report.binaryTexture={url:'atp:/browser-lab/checker.png',bytes:received.length,sha256:sha(received),rendererRequests:textureResponses};
    await writeFile(path.join(repo,'build/browser-lab/http/command.json'),JSON.stringify({sequence:Date.now(),position:{x:2,y:1.8,z:-1}})+'\n');
    await page.waitForFunction(()=>window.__assetProof.avatars.some(a=>a.displayName==='Native-Lab-Participant'&&Math.abs(a.position.x-2)<.1&&Math.abs(a.position.z+1)<.1),null,{timeout:10000});
    await page.locator('#world canvas').focus();await page.keyboard.press('KeyV');await page.waitForTimeout(1000);
    const cdp=await page.context().newCDPSession(page);
    let timer;
    try {
        const capture=await Promise.race([cdp.send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false}),
            new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Actual peer viewport capture timed out')),15000);})]);
        await writeFile(path.join(directory,'world-native-peer.png'),Buffer.from(capture.data,'base64'));
    }finally{clearTimeout(timer);await cdp.detach();}
    report.avatarSnapshot=await page.evaluate(()=>window.__assetProof.avatars);
    report.pose=await page.evaluate(()=>window.__overte.pose);
    report.events=await page.locator('#events').textContent();
    report.screenshot='world-native-peer.png';
    assert.deepEqual(errors,[],'Actual assets and avatar rendering emits no application errors');
    await page.locator('#leave').click();
    report.completed=true;
} catch(error){report.error=error.message;process.exitCode=1;console.error(error);}
finally{await browser?.close();report.finishedAt=new Date().toISOString();await writeFile(path.join(directory,'assets-and-avatars.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
