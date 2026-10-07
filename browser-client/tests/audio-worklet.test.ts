// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import assert from 'node:assert/strict';

function worklet(rate=48000) {
    let Constructor: any;
    const messages: any[] = [];
    const context = vm.createContext({
        AudioWorkletProcessor: class { port = {onmessage:null, postMessage:(message:any) => messages.push(message)}; },
        registerProcessor: (_name:string, value:any) => { Constructor = value; },
        sampleRate: rate,
        Float32Array, ArrayBuffer, DataView, Math,
    });
    vm.runInContext(readFileSync(new URL('../src/audio-worklet.js', import.meta.url), 'utf8'), context);
    const processor = new Constructor();
    return {processor, messages};
}
test('capture is silent by default, enabled mono capture is framed and little endian', () => {
    const {processor, messages} = worklet();
    const input = new Float32Array(128).fill(0.5);
    const output = [new Float32Array(128),new Float32Array(128)];
    for (let i=0;i<10;i++) processor.process([[input]], [output]);
    assert.equal(messages.length, 0);
    processor.port.onmessage({data:{type:'mute',muted:false}});
    for (let i=0;i<15;i++) processor.process([[input]], [output]);
    assert.equal(messages.length, 2);
    assert.equal(messages[0].buffer.byteLength, 1920);
    assert.equal(new DataView(messages[0].buffer).getInt16(0,true), 16384);
    processor.port.onmessage({data:{type:'mute',muted:true}});
    processor.process([[input]], [output]);
    assert.equal(messages.length, 2);
});
test('received stereo mix is preserved and queue is bounded after playback stalls', () => {
    const {processor} = worklet();
    const buffer = new ArrayBuffer(960*4);
    const view = new DataView(buffer);
    for (let i=0;i<960;i++) {view.setInt16(i*4,8192,true);view.setInt16(i*4+2,-8192,true);}
    for (let i=0;i<100;i++) processor.port.onmessage({data:{type:'pcm',buffer}});
    assert.ok(processor.frames <= 12000);
    const output = [new Float32Array(128),new Float32Array(128)];
    processor.process([[]], [output]);
    assert.equal(output[0][0],0.25);
    assert.equal(output[1][0],-0.25);
    for (let i=0;i<120;i++) processor.process([[]], [output]);
    assert.equal(processor.frames,0);
});
test('capture uses the actual context rate when 48 kHz is unavailable', () => {
    const {processor,messages} = worklet(44100);
    processor.port.onmessage({data:{type:'mute',muted:false}});
    for(let i=0;i<441;i++) processor.process([[new Float32Array(100)]],[[new Float32Array(100),new Float32Array(100)]]);
    assert.equal(messages.length,50);
});
