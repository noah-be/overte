// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('late microphone permission cannot resume capture after muting or leaving', async ({page}) => {
    await page.route('**/', route => route.fulfill({contentType:'text/html',body:'<!doctype html><body><button>Enable audio test</button></body>'}));
    await page.goto('/');
    // Resume the real AudioContext after trusted user activation, as the application does.
    await page.getByRole('button', {name:'Enable audio test'}).click();
    const result = await page.evaluate(async () => {
        const path = '/src/audio.ts';
        const {BrowserAudio} = await import(/* @vite-ignore */ path);
        let resolve: (stream:MediaStream) => void = () => {};
        let requested = false;
        let stopped = 0;
        Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async () => {
            requested = true;
            return new Promise<MediaStream>(complete => {resolve=complete;});
        }});
        const audio = new BrowserAudio(() => {},() => {});
        const enabled = audio.enableMicrophone();
        while (!requested) await new Promise(complete => setTimeout(complete,10));
        audio.stopMicrophone();
        resolve({getTracks:()=>[{stop:()=>stopped++}]} as unknown as MediaStream);
        const accepted = await enabled;
        await audio.dispose();
        return {accepted,muted:audio.muted,stopped};
    });
    expect(result).toEqual({accepted:false,muted:true,stopped:1});
});
