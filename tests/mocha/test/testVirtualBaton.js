"use strict";

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const batonSources = Object.fromEntries(Object.entries({
    developer: '../../../scripts/developer/libraries/virtualBaton.js',
    home: '../../../unpublishedScripts/DomainContent/Home/virtualBaton.js'
}).map(([name, relativePath]) => [name, new vm.Script(
    fs.readFileSync(path.join(__dirname, relativePath), 'utf8'), {filename: relativePath})]));

// The library reads Date.now() and Math.random() directly as well as using Script
// timers. Isolate all three in a VM so elections are reproducible without changing
// application code or replacing process-wide globals used by the test runner.
function makeClock() {
    let now = 1000000;
    let nextId = 1;
    const timers = new Map();
    const messages = [];
    function schedule(callback, delay, interval) {
        const id = nextId++;
        timers.set(id, {id, callback, at: now + delay, interval});
        return id;
    }
    function drainMessages() {
        let remaining = 100000;
        while (messages.length) {
            assert.ok(remaining-- > 0, 'message delivery must reach an idle state');
            messages.shift()();
        }
    }
    return {
        now: () => now,
        enqueue: callback => messages.push(callback),
        Script: {
            setTimeout: (callback, delay) => schedule(callback, delay, 0),
            clearTimeout: id => timers.delete(id),
            setInterval: (callback, delay) => schedule(callback, delay, delay),
            clearInterval: id => timers.delete(id)
        },
        advance(milliseconds) {
            const end = now + milliseconds;
            let remaining = 100000;
            drainMessages();
            while (true) {
                const next = [...timers.values()]
                    .filter(timer => timer.at <= end)
                    .sort((a, b) => a.at - b.at || a.id - b.id)[0];
                if (!next) {
                    break;
                }
                assert.ok(remaining-- > 0, 'timers must make progress');
                now = next.at;
                if (next.interval) {
                    next.at += next.interval;
                } else {
                    timers.delete(next.id);
                }
                next.callback();
                drainMessages();
            }
            now = end;
        },
        assertIdle() {
            drainMessages();
            assert.equal(timers.size, 0, 'unload must clear every timer');
            assert.equal(messages.length, 0, 'no queued messages may escape a test');
        }
    };
}

function makeHarness(t, mode, optimize, {source, realTime = false, seed = 42}) {
    const clock = realTime ? null : makeClock();
    const nodes = [];
    const batons = [];
    const owners = new Set();
    const trace = [];
    let messageCount = 0;
    const batonName = t.name;
    const random = Object.create(Math);
    random.random = () => {
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        return seed / 0x100000000;
    };
    const context = {
        module: {exports: {}},
        Date: clock ? {now: clock.now} : Date,
        Math: random
    };
    batonSources[source].runInNewContext(context);
    const virtualBaton = context.module.exports;
    const activeTimers = new Set();
    const activeIntervals = new Set();
    const realScript = {
        setTimeout(callback, delay) {
            const handle = setTimeout(() => {
                activeTimers.delete(handle);
                callback();
            }, delay);
            activeTimers.add(handle);
            return handle;
        },
        clearTimeout(handle) {
            clearTimeout(handle);
            activeTimers.delete(handle);
        },
        setInterval(callback, delay) {
            const handle = setInterval(callback, delay);
            activeIntervals.add(handle);
            return handle;
        },
        clearInterval(handle) {
            clearInterval(handle);
            activeIntervals.delete(handle);
        }
    };

    function makeMessages(me) {
        function deliver(channel, message, skip) {
            for (const node of nodes) {
                if (node !== skip && node.channels.has(channel) && node.receiver) {
                    node.receiver(channel, message, me.name);
                }
            }
        }
        return {
            subscribe: channel => me.channels.add(channel),
            unsubscribe: channel => me.channels.delete(channel),
            sendMessage(channel, message) {
                messageCount++;
                if (mode === 'immediate') {
                    deliver(channel, message);
                    return;
                }
                if (mode === 'immediate2Me' && me.channels.has(channel) && me.receiver) {
                    me.receiver(channel, message, me.name);
                }
                const delivery = () => deliver(channel, message, mode === 'immediate2Me' ? me : null);
                if (clock) {
                    clock.enqueue(delivery);
                } else {
                    process.nextTick(delivery);
                }
            },
            messageReceived: {
                connect: receiver => { me.receiver = receiver; },
                disconnect: receiver => {
                    assert.equal(me.receiver, receiver);
                    me.receiver = null;
                }
            }
        };
    }

    t.after(() => {
        for (const baton of batons) {
            baton.unload();
        }
        assert.ok(nodes.every(node => node.channels.size === 0 && node.receiver === null),
            'unload must disconnect all message receivers and subscriptions');
        if (clock) {
            clock.assertIdle();
        } else {
            const leftoverTimers = activeTimers.size + activeIntervals.size;
            // Clean up even when the assertion fails, so a regression cannot hang Node.
            activeTimers.forEach(clearTimeout);
            activeIntervals.forEach(clearInterval);
            assert.equal(leftoverTimers, 0, 'unload must clear every timer');
        }
    });

    return {
        trace,
        messageCount: () => messageCount,
        advance: milliseconds => clock.advance(milliseconds),
        add(name) {
            const node = {name, channels: new Set(), receiver: null};
            nodes.push(node);
            const baton = virtualBaton({
                batonName,
                useOptimizations: optimize,
                electionTimeout: realTime ? 20 : 100,
                recheckInterval: realTime ? 20 : 100,
                connectionTest: id => nodes.some(other => other.name === id && other.receiver),
                globals: {
                    Messages: makeMessages(node),
                    MyAvatar: {sessionUUID: name},
                    Script: clock ? clock.Script : realScript,
                    AvatarList: {getAvatar: id => ({sessionUUID: id})},
                    Entities: {getEntityProperties: () => undefined},
                    print: () => {}
                }
            });
            batons.push(baton);
            return {
                claim(onClaim = () => {}, onRelease = () => {}) {
                    let claimed = false;
                    let released = false;
                    baton.claim(key => {
                        assert.equal(key, batonName);
                        assert.equal(owners.size, 0, 'a claim must never overlap another owner');
                        assert.equal(claimed, false, 'each claim callback must run once');
                        claimed = true;
                        owners.add(name);
                        trace.push('claim ' + name);
                        onClaim();
                    }, key => {
                        assert.equal(key, batonName);
                        assert.equal(released, false, 'each release callback must run once');
                        released = true;
                        assert.ok(owners.delete(name), 'release must follow ownership');
                        trace.push('release ' + name);
                        onRelease();
                    });
                },
                release: () => baton.release()
            };
        }
    };
}

for (const source of Object.keys(batonSources)) {
    for (const optimize of [true, false]) {
        for (const mode of ['delayed', 'immediate2Me', 'immediate']) {
            const suffix = source + '-' + mode + (optimize ? '-opt' : '-unoptimized');

            test('single-' + suffix, t => {
                const harness = makeHarness(t, mode, optimize, {source});
                const a = harness.add('a');
                a.claim();
                harness.advance(5000);
                assert.deepEqual(harness.trace, ['claim a']);
            });

            test('dual-parallel-' + suffix, t => {
                const harness = makeHarness(t, mode, optimize, {source});
                const a = harness.add('a');
                const b = harness.add('b');
                a.claim();
                b.claim();
                harness.advance(5000);
                assert.equal(harness.trace.length, 1, 'exactly one claimant must win and retain ownership');
                assert.match(harness.trace[0], /^claim [ab]$/);
            });

            for (const delay of [500, 3000]) {
                test('dual-serial-' + delay + 'ms-' + suffix, t => {
                    const harness = makeHarness(t, mode, optimize, {source});
                    harness.add('a').claim();
                    harness.advance(delay);
                    assert.deepEqual(harness.trace, ['claim a']);
                    harness.add('b').claim();
                    // Observe well past the second claimant's election and recheck timers.
                    harness.advance(5000);
                    assert.deepEqual(harness.trace, ['claim a'], 'a late claimant must not steal a held baton');
                });
            }

            test('dual-serial-with-release-' + suffix, t => {
                const harness = makeHarness(t, mode, optimize, {source});
                const a = harness.add('a');
                const b = harness.add('b');
                a.claim(() => {
                    b.claim();
                    a.release();
                });
                harness.advance(5000);
                assert.deepEqual(harness.trace, ['claim a', 'release a', 'claim b']);
            });

            test('settled-waiter-with-release-' + suffix, t => {
                const harness = makeHarness(t, mode, optimize, {source});
                const a = harness.add('a');
                const b = harness.add('b');
                a.claim();
                harness.advance(1000);
                assert.deepEqual(harness.trace, ['claim a']);
                b.claim();
                harness.advance(1000);
                assert.deepEqual(harness.trace, ['claim a']);
                a.release();
                harness.advance(5000);
                assert.deepEqual(harness.trace, ['claim a', 'release a', 'claim b']);
                b.release();
                harness.advance(1000);
                assert.deepEqual(harness.trace, ['claim a', 'release a', 'claim b', 'release b']);
                const settledMessages = harness.messageCount();
                harness.advance(1000);
                assert.equal(harness.messageCount(), settledMessages,
                    'a free baton without waiting claimants must stop holding elections');
                a.claim();
                harness.advance(1000);
                assert.deepEqual(harness.trace, ['claim a', 'release a', 'claim b', 'release b', 'claim a']);
            });

            test('settled-competing-waiters-with-release-' + suffix, t => {
                const harness = makeHarness(t, mode, optimize, {source});
                const a = harness.add('a');
                const b = harness.add('b');
                const c = harness.add('c');
                a.claim();
                harness.advance(1000);
                b.claim();
                c.claim();
                harness.advance(1000);
                assert.deepEqual(harness.trace, ['claim a']);
                a.release();
                harness.advance(5000);
                assert.equal(harness.trace.length, 3, 'exactly one waiting claimant must take ownership');
                assert.match(harness.trace[2], /^claim [bc]$/);
                const winner = harness.trace[2] === 'claim b' ? b : c;
                const first = winner === b ? 'b' : 'c';
                const next = winner === b ? 'c' : 'b';
                winner.release();
                harness.advance(5000);
                assert.deepEqual(harness.trace,
                    ['claim a', 'release a', 'claim ' + first, 'release ' + first, 'claim ' + next]);
            });

            for (const seed of [42, 8]) {
                test('dual-parallel-with-release-' + suffix + '-seed' + seed, t => {
                    const harness = makeHarness(t, mode, optimize, {source, seed});
                    const a = harness.add('a');
                    const b = harness.add('b');
                    a.claim(() => a.release());
                    b.claim();
                    harness.advance(5000);
                    const aWonFirst = harness.trace[0] === 'claim a';
                    assert.deepEqual(harness.trace, aWonFirst
                        ? ['claim a', 'release a', 'claim b'] : ['claim b']);
                    b.release();
                    harness.advance(1000);
                    assert.deepEqual(harness.trace, aWonFirst
                        ? ['claim a', 'release a', 'claim b', 'release b']
                        : ['claim b', 'release b', 'claim a', 'release a']);
                });
            }
        }
    }

    // Keep an actual event-loop smoke test in addition to deterministic interleavings.
    // The runner waits for B's ownership and release, with a bounded failure timeout.
    test('real event-loop handoff-' + source, {timeout: 5000}, async t => {
        const harness = makeHarness(t, 'delayed', true, {source, realTime: true});
        const a = harness.add('a');
        const b = harness.add('b');
        await new Promise(resolve => {
            a.claim(() => {
                b.claim(() => {
                    b.release();
                    resolve();
                });
                a.release();
            });
        });
        // Drain follow-up elections after release before checking for duplicate events.
        await new Promise(resolve => setTimeout(resolve, 200));
        assert.deepEqual(harness.trace, ['claim a', 'release a', 'claim b', 'release b']);
    });
}
