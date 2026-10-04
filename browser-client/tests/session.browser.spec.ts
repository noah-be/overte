// SPDX-License-Identifier: Apache-2.0
// Isolated UI/protocol tests. Real native-domain acceptance is recorded separately.
import { test, expect } from '@playwright/test';

async function fixture(page:any, options:{denyMicrophone?:boolean; failure?:boolean}={}) {
    await page.route('**/api/config', (route:any) => route.fulfill({json:{domains:[{name:'Test domain',address:'overte://127.0.0.1:45102'}]}}));
    await page.route('**/api/session', (route:any) => route.fulfill({json:{ready:true}}));
    if (options.denyMicrophone) await page.addInitScript(() => {
        Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {value:async () => {
            throw new DOMException('Permission denied', 'NotAllowedError');
        }});
    });
    await page.routeWebSocket('**/session', (socket:any) => {
        socket.onMessage((raw:string) => {
            const message = JSON.parse(raw);
            if (message.type !== 'join') return;
            if (options.failure) {
                socket.send(JSON.stringify({type:'state',state:'error',message:'Domain denied this visitor connection.'}));
                return;
            }
            socket.send(JSON.stringify({type:'state',state:'connected',sessionId:'test-session',permissionRevision:1}));
            socket.send(JSON.stringify({type:'pose',position:{x:0,y:1,z:0}}));
            socket.send(JSON.stringify({type:'entities',entities:[{id:'floor',type:'Box',position:{x:0,y:-0.25,z:0},dimensions:{x:20,y:0.5,z:20},color:{red:110,green:140,blue:160}}]}));
            socket.send(JSON.stringify({type:'avatars',selfId:'self',avatars:[{id:'native',displayName:'Native visitor',position:{x:2,y:1,z:-3}}]}));
            // Domains may repeat their state; this must not clear held controls or mute voice.
            let count = 0;
            const heartbeat = setInterval(() => {
                if (++count > 10) { clearInterval(heartbeat); return; }
                socket.send(JSON.stringify({type:'state',state:'connected',sessionId:'test-session',permissionRevision:1}));
            },100);
            socket.onClose(() => clearInterval(heartbeat));
        });
    });
}

test('domain selection, join, clean leave and reconnect are usable', async ({page}) => {
    await fixture(page);
    await page.goto('/');
    await expect(page.locator('#domain')).toHaveValue('overte://127.0.0.1:45102');
    await page.locator('#join').click();
    await expect(page.locator('#connection')).toHaveAttribute('data-state','connected');
    await expect(page.locator('#stats')).toHaveText('1 entities · 1 other participants');
    await expect(page.locator('#microphone')).toHaveAttribute('aria-pressed','false');
    await page.locator('#world canvas').focus();
    await page.keyboard.down('KeyW');
    // Observe movement rather than assuming a software-rendered frame rate.
    // Keep the key held through repeated connection notifications.
    await expect.poll(() => page.evaluate(() => (window as any).__overte.pose.position.z)).toBeLessThan(-1);
    await page.keyboard.up('KeyW');
    expect(await page.evaluate(() => (window as any).__overte.pose.position.z)).toBeLessThan(-1);
    await page.locator('#leave').click();
    await expect(page.locator('#welcome')).toBeVisible();
    await expect(page.locator('#world canvas')).toHaveCount(0);
    await page.locator('#join').click();
    await expect(page.locator('#connection')).toHaveAttribute('data-state','connected');
    await expect(page.locator('#world canvas')).toHaveCount(1);
});

test('denied microphone leaves the world usable and explains recovery', async ({page}) => {
    await fixture(page,{denyMicrophone:true});
    await page.goto('/');
    await page.locator('#join').click();
    await expect(page.locator('#connection')).toHaveAttribute('data-state','connected');
    await page.locator('#microphone').click();
    await expect(page.locator('#notice')).toContainText('Microphone permission denied');
    await expect(page.locator('#microphone')).toHaveAttribute('aria-pressed','false');
    await expect(page.locator('#connection')).toHaveAttribute('data-state','connected');
    await page.locator('#sound').click();
    await expect(page.locator('#sound')).toHaveAttribute('aria-pressed','false');
});

test('permission-denied connection returns to the join screen with error intact', async ({page}) => {
    await fixture(page,{failure:true});
    await page.goto('/');
    await page.locator('#join').click();
    await expect(page.locator('#notice')).toContainText('Domain denied this visitor connection.');
    await expect(page.locator('#welcome')).toBeVisible();
    await expect(page.locator('#join')).toBeEnabled();
});

test('small screens keep domain join and leave controls reachable', async ({page}) => {
    await page.setViewportSize({width:390,height:844});
    await fixture(page);
    await page.goto('/');
    await expect(page.locator('#join')).toBeInViewport();
    await page.locator('#join').click();
    await expect(page.locator('#leave')).toBeInViewport();
});

test('transient domain reconnect clears stale content and loads a fresh snapshot', async ({page}) => {
    await page.route('**/api/config', route => route.fulfill({json:{domains:[]}}));
    await page.route('**/api/session', route => route.fulfill({json:{ready:true}}));
    let send: (message:object) => void = () => { throw new Error('Socket not ready'); };
    const entities = [{id:'floor',type:'Box',position:{x:0,y:-0.25,z:0},dimensions:{x:20,y:0.5,z:20}}];
    await page.routeWebSocket('**/session', socket => {
        send = message => socket.send(JSON.stringify(message));
        socket.onMessage(raw => {
            if (JSON.parse(String(raw)).type !== 'join') return;
            send({type:'state',state:'connected',sessionId:'test-session',permissionRevision:1});
            send({type:'entities',entities});
            send({type:'avatars',avatars:[{id:'native',position:{x:2,y:1,z:-3}}]});
        });
    });
    await page.goto('/');
    await page.locator('#domain').fill('overte://127.0.0.1:45102');
    await page.locator('#join').click();
    await expect(page.locator('#stats')).toHaveText('1 entities · 1 other participants');
    send({type:'state',state:'connecting',sessionId:'test-session'});
    await expect(page.locator('#stats')).toHaveText('0 entities · 0 other participants');
    await expect(page.locator('#loading')).toBeVisible();
    send({type:'state',state:'connected',sessionId:'test-session',permissionRevision:1});
    send({type:'entities',entities});
    await expect(page.locator('#stats')).toHaveText('1 entities · 0 other participants');
    await expect(page.locator('#loading')).toBeHidden();
    await page.locator('#world canvas').focus();
    await page.keyboard.down('KeyW');
    await expect.poll(() => page.evaluate(() => (window as any).__overte.pose.position.z)).toBeLessThan(-0.5);
    await page.keyboard.up('KeyW');
});
