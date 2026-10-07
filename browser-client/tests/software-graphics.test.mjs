// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {chromiumGraphicsArgs} from './software-graphics.mjs';

const source = name => readFileSync(new URL(name, import.meta.url), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

test('explicit software fixtures use SwiftShader on a virtual display as well as headless', () => {
    for (const headless of [false, true]) assert.deepEqual(chromiumGraphicsArgs({headless, software:'true'}), ['--use-angle=swiftshader']);
    assert.deepEqual(chromiumGraphicsArgs({headless:true, software:undefined}), ['--use-angle=swiftshader']);
    for (const software of [undefined, '', 'false', 'TRUE']) assert.deepEqual(chromiumGraphicsArgs({headless:false, software}), []);
});

function context(display, software) {
    return {display, browserKind:'chrome', isChromium:true, browserPulse:'unix:/owned/audio',
        evidenceDirectory:'/owned/evidence', process:{env:{LIBGL_ALWAYS_SOFTWARE:software}},
        googleChromeLaunchOptions:() => ({channel:'chrome'}),
        chromiumGraphicsArgs:options => chromiumGraphicsArgs({...options, software}),
        chromium:{launch:async options => options}, firefox:{launch:() => {throw Error('Unexpected Firefox');}}};
}

test('actual Core launcher requests the software backend without changing microphone flags or branded Chrome', async () => {
    const text=source('./integration/real-session.mjs'), start=text.indexOf('async function startBrowser()'), end=text.indexOf('\nasync function screenshot(', start);
    assert(start>=0 && end>start);
    for (const software of ['true', undefined]) {
        const c=context(':owned',software);c.process.env.OVERTE_LAB_BROWSER_DISPLAY=':owned';
        const options=await vm.runInNewContext(text.slice(start,end)+'\nstartBrowser();',c);
        assert.equal(options.channel,'chrome');assert.equal(options.headless,false);
        assert.deepEqual(plain(options.args),[...(software==='true'?['--use-angle=swiftshader']:[]),
            '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture=/owned/evidence/browser-microphone.wav']);
        assert.deepEqual(plain(options.ignoreDefaultArgs),['--mute-audio']);
    }
});

test('actual pruning launcher requests software while preserving the original real pixel proof', async () => {
    const text=source('./integration/native-ignored-fbx-pixels.mjs'), statement=text.split('\n').find(line=>line.startsWith(' else {if(engine==='));
    assert(statement);
    for (const software of ['true', undefined]) {
        const c={...context(':owned',software),engine:'chrome',env:{},browser:null,assert};
        const options=await vm.runInNewContext('(async()=>{if(false){}'+statement+'return browser;})()',c);
        assert.equal(options.channel,'chrome');assert.equal(options.headless,false);
        assert.deepEqual(plain(options.args),['--mute-audio',...(software==='true'?['--use-angle=swiftshader']:[])]);
    }
    assert(text.includes("setTimeout(()=>reject(Error('Native ignored FBX pixel fixture exceeded 30 seconds')),30000)"));
    const fixture=source('./fixtures/native-ignored-fbx-pixels.ts');
    assert(fixture.includes("assert(glErrorCode===0,'Actual GPU render produced a GL error')"));
    assert(fixture.includes("assert(output.every((value,index)=>value===original[index]),'Original/pruned actual GPU pixels differ')"));
    assert(fixture.includes('frame<20'));
});
