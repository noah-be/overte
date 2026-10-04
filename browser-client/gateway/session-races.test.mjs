import {PushToTalkSession} from './push-to-talk.mjs';
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import { SharedTeardown } from './process-lifecycle.mjs';
import { managedUDPDomain } from './validation.mjs';
import { managedNavigationSelection } from './navigation.mjs';
import { validateVisitorPreferences } from '../shared/visitor-preferences.mjs';
import { validateVisitorPersona, WEARABLE_FIELDS } from '../shared/visitor-persona.mjs';
import {acceptedNativePersona} from './visitor-persona.mjs';

// Execute the production Session teardown and message handler, replacing only
// external native launch with a deferred operation. No domain or service is used.
async function connectionHarness() {
    const source = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
    const classStart = source.indexOf('class Session extends SharedTeardown {');
    const classEnd = source.indexOf('\nconst server = http.createServer', classStart);
    const handlerStart = source.indexOf("browserServer.on('connection'");
    const handlerEnd = source.indexOf("nativeServer.on('connection'", handlerStart);
    assert.ok(classStart >= 0 && classEnd > classStart && handlerStart > classEnd && handlerEnd > handlerStart);
    const sessions = new Map(), sockets = new Set(), messages = [], launches = [], created = [];
    const browser = {readyState:1,on(name, listener) { this[name] = listener; }};
    const send = (socket, message) => { if (socket === browser) messages.push(message); };
    const classContext = {PushToTalkSession, SharedTeardown, randomBytes, randomUUID, clearTimeout, sessions, send,
        WebSocket:{OPEN:1}};
    const GatewaySession = vm.runInNewContext(
        source.slice(classStart, classEnd).replace('class Session extends', 'class GatewaySession extends') + '\nGatewaySession;',
        classContext,
    );
    class DeferredSession extends GatewaySession {
        constructor(...args) { super(...args); created.push(this); }
        launch() { return new Promise((resolve, reject) => launches.push({resolve, reject, session:this})); }
    }
    vm.runInNewContext(source.slice(handlerStart, handlerEnd), {
        Session:DeferredSession, sessions, sockets, maximumSessions:4, shuttingDown:false,
        cookie:() => 'owned-session-cookie', send, pose:() => {}, WebSocket:{OPEN:1}, equal:(a,b)=>a===b,
        browserServer:{on(event, listener) { assert.equal(event, 'connection'); listener(browser, {headers:{}}); }},
    });
    return {messages, launches, created, sessions,
        dispatch:message => browser.message(Buffer.from(JSON.stringify(message)), false),
        async dispose() {
            for (const launch of launches) launch.resolve();
            await Promise.all(created.map(session => session.close(false)));
        },
    };
}

test('an obsolete launch failure cannot close or report errors to a replacement session', async t => {
    const state = await connectionHarness(); t.after(() => state.dispose());
    const first = state.dispatch({type:'join', domain:'overte://managed.example'});
    const leaving = state.dispatch({type:'leave'});
    assert.equal(state.created[0].closed, true, 'Leave revokes the old session immediately');
    const replacement = state.dispatch({type:'join', domain:'overte://managed.example'});
    assert.equal(state.launches.length, 2);
    assert.equal(state.created[1].closed, false);
    state.launches[0].reject(Error('Session cancelled.'));
    state.launches[1].resolve();
    await Promise.all([first, leaving, replacement]);
    assert.equal(state.created[1].closed, false, 'An old launch must not clean up the replacement');
    assert.equal(state.sessions.has(state.created[1].id), true);
    assert.deepEqual(state.messages, [], 'Old errors and teardown notices must not reset the replacement UI');
});

test('an overlapping join is rejected without closing the current pending launch', async t => {
    const state = await connectionHarness(); t.after(() => state.dispose());
    const pending = state.dispatch({type:'join', domain:'overte://managed.example'});
    const rejected = state.dispatch({type:'join', domain:'overte://managed.example'});
    assert.equal(state.launches.length, 1, 'Rejected joins cannot allocate another native connection');
    assert.equal(state.created[0].closed, false, 'Rejecting an overlapping join must retain the active launch');
    await rejected;
    assert.equal(state.sessions.size, 1);
    assert.equal(state.messages.length, 1);
    assert.equal(state.messages[0].state, 'error');
    assert.match(state.messages[0].message, /Leave your current domain/);
    state.launches[0].resolve(); await pending;
});

test('cancelling a pending join reports clean leave instead of a stale launch error', async t => {
    const state = await connectionHarness(); t.after(() => state.dispose());
    const joining = state.dispatch({type:'join', domain:'overte://managed.example'});
    const leaving = state.dispatch({type:'leave'});
    assert.equal(state.created[0].closed, true);
    state.launches[0].reject(Error('Session cancelled.'));
    await Promise.all([joining, leaving]);
    assert.equal(state.sessions.size, 0);
    assert.equal(state.messages.length, 1);
    assert.equal(state.messages[0].state, 'disconnected');
    assert.equal(state.messages[0].message, 'You left the domain.');
});

test('leaving during the final bridge file write cannot spawn a late native connection', async () => {
    const source = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
    const start = source.indexOf('class Session extends SharedTeardown {');
    const end = source.indexOf('\nconst server = http.createServer', start);
    assert.ok(start >= 0 && end > start);
    const domain = 'overte://127.0.0.2:45102';
    let reachedWrite, finishWrite;
    const reached = new Promise(resolve => { reachedWrite = resolve; });
    const write = new Promise(resolve => { finishWrite = resolve; });
    const messages = [], spawns = [], terminated = [], removed = [];
    const Session = vm.runInNewContext(source.slice(start, end) + '\nSession;', {
        PushToTalkSession, SharedTeardown, randomBytes, randomUUID, path, clearTimeout, setTimeout,
        sessions:new Map(), WebSocket:{OPEN:1},
        process:{env:{OVERTE_INTERFACE:'/fixture/interface', OVERTE_GATEWAY_GUEST_POLICY:'/fixture/policy',
            OVERTE_GATEWAY_MANAGED_UDP_PORTS:'45102,45200'}}, managedUDPDomain, managedNavigationSelection, validateVisitorPreferences, validateVisitorPersona, WEARABLE_FIELDS, acceptedNativePersona,
        assetOrigins:new Set(),publicAssetOrigins:new Set(),prepareVisitorPersona:async()=>({}),
        domainAddress:value => value, domains:[domain],
        readPolicyFile:async () => new Map([[domain, {}]]), nativeDomainAddress:async value => value,
        tmpdir:() => '/tmp', mkdtemp:async () => '/tmp/fixture-session', mkdir:async () => {},
        directory:'/fixture/gateway', port:8090, nativeBridgeSource:'// fixture bridge', run:async () => {},
        writeFile:async file => { if (path.basename(file) === 'bridge.js') { reachedWrite(); await write; } },
        send:(socket, message) => messages.push(message),
        terminateProcess:async child => { terminated.push(child.label); },
        rm:async directory => { removed.push(directory); },
    });
    class LaunchSession extends Session {
        process(command, args, env, label) {
            spawns.push({label, afterClose:this.closed});
            const child = Object.assign(new EventEmitter(), {label, exitCode:null,
                stdout:new EventEmitter(), stderr:new EventEmitter(), stdin:new EventEmitter()});
            this.processes.push(child); return child;
        }
    }
    const session = new LaunchSession({}, 'owner');
    session.launching = session.launch({domain});
    await reached;
    const closing = session.close(false);
    assert.equal(session.closed, true, 'Revocation happens while the final file write is pending');
    finishWrite(); await Promise.all([assert.rejects(session.launching, /Session cancelled/), closing]);
    assert.deepEqual(spawns, [{label:'Isolated audio server', afterClose:false}]);
    assert.deepEqual(terminated, ['Isolated audio server'], 'The already-created private audio server is cleaned up');
    assert.deepEqual(removed, ['/tmp/fixture-session']);
    assert.equal(messages.some(message => message.state === 'connecting'), false,
        'A cancelled session must not publish a late connecting state');
});

test('native teardown keeps the private display and PulseAudio alive until native exit, and stops PulseAudio last', async () => {
    const source=await readFile(new URL('./server.mjs',import.meta.url),'utf8');
    const start=source.indexOf('class Session extends SharedTeardown {'),end=source.indexOf('\nconst server = http.createServer',start);
    const events=[],terminations=new Map();
    const Session=vm.runInNewContext(source.slice(start,end)+'\nSession;',{
        PushToTalkSession,SharedTeardown,randomBytes,randomUUID,clearTimeout,sessions:new Map(),WebSocket:{OPEN:1},send:()=>{},
        terminateProcess:child=>{events.push(child.label);return new Promise(resolve=>terminations.set(child.label,resolve));},
        rm:async()=>{}
    });
    const session=new Session({},'owner');
    session.nativeProcess={label:'native'};session.audioServer={label:'pulse'};
    session.processes=[session.audioServer,{label:'display'},{label:'capture'},session.nativeProcess];
    const closing=session.close(false);await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(events,['native'],'Native termination cannot destroy its live media dependencies');
    terminations.get('native')();await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(events,['native','display','capture'],'PulseAudio remains available while other media children stop');
    terminations.get('display')();await new Promise(resolve=>setImmediate(resolve));assert.equal(terminations.has('pulse'),false);
    terminations.get('capture')();await new Promise(resolve=>setImmediate(resolve));assert.equal(events.at(-1),'pulse');
    terminations.get('pulse')();await closing;
});
