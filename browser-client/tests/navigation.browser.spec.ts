// SPDX-License-Identifier: Apache-2.0
// Session-controller component proof; this fixture does not attest domain access.
import {test,expect} from '@playwright/test';
import type {WebSocketRoute} from '@playwright/test';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {WebSocketServer,type WebSocket} from 'ws';

test('Places handoff replaces the session and commits history only after new admission', async({page}) => {
    const joins:string[] = [], commands:any[] = [];
    let current:WebSocketRoute;
    await page.route('**/api/config', route => route.fulfill({json:{domains:[{name:'First',address:'overte://first'}]}}));
    await page.route('**/api/session', route => route.fulfill({json:{ready:true}}));
    await page.routeWebSocket('**/session', socket => {
        socket.onMessage(raw => {
            if (typeof raw !== 'string') return;
            const message = JSON.parse(raw); commands.push(message);
            if (message.type !== 'join') return;
            current = socket; joins.push(message.domain);
            socket.send(JSON.stringify({type:'state',state:'connected',sessionId:`session-${joins.length}`,permissionRevision:1}));
            socket.send(JSON.stringify({type:'entities',entities:[{id:'floor',type:'Box',position:{x:0,y:-.5,z:0},dimensions:{x:30,y:1,z:30}}]}));
        });
    });
    await page.goto('/');
    await page.getByRole('button',{name:/^Join world/}).click();
    await expect.poll(() => joins).toEqual(['overte://first']);
    await expect.poll(() => commands.filter(value => value.type === 'navigationHistoryState').at(-1)).toMatchObject({canGoBack:false,canGoForward:false,permissionRevision:1});
    current!.send(JSON.stringify({type:'pose',position:{x:5,y:.85,z:2},orientation:{x:0,y:1,z:0,w:0}}));
    await expect.poll(()=>page.evaluate(()=>(window as any).__overte.pose.position.x)).toBeCloseTo(5,3);
    const navigation = {type:'navigation',nonce:'12345678-abcd-1234-5678-123456789abc',permissionRevision:1,domain:'overte://second'};
    current!.send(JSON.stringify(navigation));
    await expect.poll(() => joins).toEqual(['overte://first','overte://second']);
    await expect.poll(() => commands.filter(value => value.type === 'navigationHistoryState').at(-1)).toMatchObject({canGoBack:true,canGoForward:false});
    await expect(page.locator('#world canvas')).toHaveCount(1);
    current!.send(JSON.stringify({...navigation,type:'navigationHistory',direction:'back'}));
    await expect.poll(() => joins.length).toBe(3);
    expect(joins.slice(0,2)).toEqual(['overte://first','overte://second']);
    const returned = new URL(joins[2]);
    expect(returned.hostname).toBe('first');
    const [position,orientation] = returned.pathname.slice(1).split('/').map(part=>part.split(',').map(Number));
    expect(position[0]).toBeCloseTo(5,3);expect(position[1]).toBeCloseTo(.85,2);expect(position[2]).toBeCloseTo(2,3);
    // Camera yaw reconstructs the quaternion through sin/cos; cos(PI/2)
    // has a floating-point residual even though this is the same rotation.
    expect(orientation).toHaveLength(4);
    [0,1,0,0].forEach((component,index)=>expect(orientation[index]).toBeCloseTo(component,12));
    await expect.poll(() => commands.filter(value => value.type === 'navigationHistoryState').at(-1)).toMatchObject({canGoBack:false,canGoForward:true});
    await expect(page.locator('#world canvas')).toHaveCount(1);
    current!.send(JSON.stringify({...navigation,type:'navigationHistory',direction:'back'}));
    await expect(page.locator('#notice')).toContainText('No previous world');
    expect(joins).toHaveLength(3);
    await page.getByRole('button',{name:'Leave',exact:true}).click();
    await expect(page.locator('#world canvas')).toHaveCount(0);
});

test('visitor Places preferences survive reload and reject stale native authority without copying foreign state', async({page}) => {
    const joins:any[] = [];
    let current:WebSocketRoute;
    await page.route('**/api/config',route=>route.fulfill({json:{domains:[{name:'First',address:'overte://first'}]}}));
    await page.route('**/api/session',route=>route.fulfill({json:{ready:true}}));
    await page.routeWebSocket('**/session',socket=>{
        socket.onMessage(raw=>{
            if (typeof raw !== 'string') return;
            const message = JSON.parse(raw);
            if (message.type !== 'join') return;
            current = socket; joins.push(message);
            socket.send(JSON.stringify({type:'state',state:'connected',sessionId:`prefs-${joins.length}`,permissionRevision:1}));
            socket.send(JSON.stringify({type:'entities',entities:[]}));
        });
    });
    await page.goto('/');
    await page.evaluate(()=>localStorage.setItem('other-app-account-token','synthetic private account state'));
    await page.getByRole('button',{name:/^Join world/}).click();
    await expect.poll(()=>joins.length).toBe(1);
    expect(joins[0].visitorPreferences).toEqual({bookmarks:[]});
    const preferences = {bookmarks:[{name:'Überte 世界 👋',address:'overte://overte_hub/1,2,3/0,0,0,1'}],home:'overte://first'};
    current!.send(JSON.stringify({type:'visitorPreferences',permissionRevision:2,...preferences}));
    // An unrelated native message ensures the stale packet has been processed.
    current!.send(JSON.stringify({type:'warning',message:'stale preferences processed'}));
    await expect(page.locator('#notice')).toContainText('stale preferences processed');
    expect(await page.evaluate(()=>localStorage.getItem('overte.browser.visitor-preferences.v1'))).toBeNull();
    current!.send(JSON.stringify({type:'visitorPreferences',permissionRevision:1,...preferences,accountToken:'never store or forward'}));
    await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('overte.browser.visitor-preferences.v1') || 'null'))).toEqual(preferences);
    await page.getByRole('button',{name:'Leave',exact:true}).click();
    await page.reload();
    await page.getByRole('button',{name:/^Join world/}).click();
    await expect.poll(()=>joins.length).toBe(2);
    expect(joins[1].visitorPreferences).toEqual(preferences);
    expect(JSON.stringify(joins)).not.toContain('synthetic private account state');
    expect(JSON.stringify(joins)).not.toContain('never store or forward');
    expect(await page.evaluate(()=>localStorage.getItem('other-app-account-token'))).toBe('synthetic private account state');
    await page.getByRole('button',{name:'Leave',exact:true}).click();
});

test('native avatar preferences persist across fresh joins without stale authority or foreign account data',async({page})=>{
    const joins:any[]=[];let current:WebSocketRoute;
    await page.route('**/api/config',route=>route.fulfill({json:{domains:[{name:'First',address:'overte://first'}]}}));
    await page.route('**/api/session',route=>route.fulfill({json:{ready:true}}));
    await page.routeWebSocket('**/session',socket=>{
        socket.onMessage(raw=>{
            if(typeof raw!=='string')return;const value=JSON.parse(raw);if(value.type!=='join')return;
            current=socket;joins.push(value);
            socket.send(JSON.stringify({type:'state',state:'connected',sessionId:`persona-${joins.length}`,permissionRevision:1}));
        });
    });
    await page.goto('/');await page.getByRole('button',{name:/^Join world/}).click();
    await expect.poll(()=>joins.length).toBe(1);
    const persona={displayName:'Überte 世界 👋',avatarURL:'https://content.overte.org/avatars/Kim.fst',avatarScale:1.5,
        avatarFavorites:[{name:'My Kim',avatarURL:'https://content.overte.org/avatars/Kim.fst',avatarScale:1.5}]};
    current!.send(JSON.stringify({type:'visitorPersona',permissionRevision:2,...persona}));
    current!.send(JSON.stringify({type:'warning',message:'stale persona processed'}));
    await expect(page.locator('#notice')).toContainText('stale persona processed');
    expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('overte.browser.visitor-persona.v1')!))).toEqual({displayName:'Browser visitor'});
    current!.send(JSON.stringify({type:'visitorPersona',permissionRevision:1,...persona,accountToken:'never copy this synthetic field'}));
    await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('overte.browser.visitor-persona.v1')!))).toEqual(persona);
    // A partial native update must retain the saved favorites collection.
    current!.send(JSON.stringify({type:'visitorPersona',permissionRevision:1,avatarScale:2}));
    await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('overte.browser.visitor-persona.v1')!).avatarScale)).toBe(2);
    await page.getByRole('button',{name:'Leave',exact:true}).click();await page.reload();
    await expect(page.locator('#name')).toHaveValue(persona.displayName);
    await page.getByRole('button',{name:/^Join world/}).click();await expect.poll(()=>joins.length).toBe(2);
    expect(joins[1].visitorPersona).toEqual({...persona,avatarScale:2});expect(joins[1].displayName).toBe(persona.displayName);
    expect(JSON.stringify(joins)).not.toContain('never copy');
    current!.send(JSON.stringify({type:'visitorPersona',permissionRevision:1,avatarFavorites:[]}));
    await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('overte.browser.visitor-persona.v1')!).avatarFavorites)).toEqual([]);
    await page.getByRole('button',{name:'Leave',exact:true}).click();
});

test('malformed gateway messages close the actual browser socket and permit a fresh join', async({page}) => {
    let current:WebSocket, joins = 0;
    const closes:{code:number;reason:string}[] = [], errors:string[] = [];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/');
    const html = (await readFile(new URL('../index.html',import.meta.url),'utf8'))
        .replace('src="/src/main.ts"',`src="${new URL(page.url()).origin}/src/main.ts"`);
    const server = createServer((request,response)=>{
        response.setHeader('Content-Type',request.url?.startsWith('/api/') ? 'application/json' : 'text/html');
        response.end(request.url === '/api/config' ? JSON.stringify({domains:[{name:'First',address:'overte://first'}]})
            : request.url === '/api/session' ? JSON.stringify({ready:true}) : html);
    });
    const sockets = new WebSocketServer({server});
    sockets.on('connection',socket=>{
        socket.on('close',(code,reason)=>closes.push({code,reason:reason.toString()}));
        socket.on('message',raw=>{
            if (JSON.parse(raw.toString()).type !== 'join') return;
            current = socket; joins++;
            socket.send(JSON.stringify({type:'state',state:'connected',sessionId:`protocol-${joins}`,permissionRevision:1}));
        });
    });
    await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
    const address = server.address();
    if (!address || typeof address === 'string') throw Error('Actual test socket did not open');
    try {
        await page.goto(`http://127.0.0.1:${address.port}`);
        await page.getByRole('button',{name:/^Join world/}).click();
        await expect.poll(()=>joins).toBe(1);
        current!.send('{malformed');
        await expect.poll(()=>closes).toEqual([{code:4002,reason:'Protocol error'}]);
        await expect(page.locator('#notice')).toContainText('Gateway protocol error');
        await expect(page.locator('#world canvas')).toHaveCount(0);
        await expect(page.getByRole('button',{name:/^Join world/})).toBeEnabled();
        await page.getByRole('button',{name:/^Join world/}).click();
        await expect.poll(()=>joins).toBe(2);
        expect(errors).toEqual([]);
        await page.getByRole('button',{name:'Leave',exact:true}).click();
    } finally {
        await page.goto('about:blank');
        for (const socket of sockets.clients) socket.terminate();
        await new Promise<void>(resolve=>sockets.close(()=>resolve()));
        await new Promise<void>(resolve=>server.close(()=>resolve()));
    }
});
