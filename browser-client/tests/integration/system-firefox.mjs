// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Preserve the real-domain journey while driving an unpatched installed Firefox over WebDriver BiDi.
// Primary references: https://pptr.dev/api/puppeteer.launchoptions and https://pptr.dev/next/webdriver-bidi
// Fake-media preferences: https://searchfox.org/firefox-main/source/modules/libpref/init/all.js
import puppeteer from 'puppeteer-core';

/** Prefer a public WM resize at native density. Fractional-DPI WM quantization
 * can make an exact inner dimension unreachable; a public viewport fallback
 * is admitted by independently observed effect, never by RPC ACK alone.
 */
export async function sizeSystemFirefoxWindow(browser, page, viewport) {
    if (![viewport?.width, viewport?.height].every(value => Number.isSafeInteger(value) && value > 0)) throw Error('Invalid actual Firefox window dimensions.');
    const started = Date.now(), deadline = started + 10000;
    const expiry = () => Error('The actual Firefox viewport did not reach its exact dimensions within ten seconds.');
    const bounded = async operation => {
        const remaining = deadline - Date.now();
        if (remaining <= 0) throw expiry();
        let timer;
        try {
            return await Promise.race([Promise.resolve().then(() => {if (deadline-Date.now() <= 0) throw expiry();return operation();}),new Promise((_,reject) => {timer=setTimeout(() => reject(expiry()),remaining);})]);
        } finally {clearTimeout(timer);}
    };
    const read = () => bounded(() => page.evaluate(() => ({width:innerWidth,height:innerHeight,density:devicePixelRatio})));
    const initial = await read();
    if (!Number.isFinite(initial.density) || initial.density <= 0) throw Error('Invalid actual Firefox native pixel density.');
    const expected = {width:viewport.width,height:viewport.height,density:initial.density};
    const exact = value => value.width === expected.width && value.height === expected.height && value.density === expected.density;
    const windowID = await bounded(() => page.windowId());
    let attempts = 0;
    const admit = async (method,acknowledgement) => {
        const actual = await read();
        if (!exact(actual) || await bounded(() => page.windowId()) !== windowID) throw Error('The owned Firefox viewport or native density changed before admission.');
        return {method,boundsAttempts:attempts,viewportAcknowledgementAtReturn:acknowledgement,
            requested:{width:viewport.width,height:viewport.height},actual,durationMs:Date.now()-started};
    };
    if (exact(initial)) return await admit('public-window','not-requested');
    await bounded(() => browser.setWindowBounds(windowID,{windowState:'normal'}));
    let requestedBounds;
    for (; attempts < 3;) {
        const bounds = await bounded(() => browser.getWindowBounds(windowID)), inner = await read();
        if (exact(inner)) return await admit('public-window','not-requested');
        requestedBounds = {windowState:'normal',width:viewport.width+(requestedBounds?.width??bounds.width)-inner.width,
            height:viewport.height+(requestedBounds?.height??bounds.height)-inner.height};
        attempts++;
        await bounded(() => browser.setWindowBounds(windowID,requestedBounds));
        try {
            const result = await bounded(() => page.waitForFunction(size => innerWidth === size.width && innerHeight === size.height && devicePixelRatio === size.density,
                {timeout:Math.min(500,deadline-Date.now())},expected));
            try { return await admit('public-window','not-requested'); } finally { await result?.dispose(); }
        } catch (error) { if (error?.name !== 'TimeoutError') throw error; }
    }
    if (deadline-Date.now() <= 0) throw expiry();
    let acknowledgement = 'pending', observedFailure, rejectFailure;
    const failure = new Promise((_,reject) => {rejectFailure=reject;});
    void failure.catch(() => {});
    // An applied viewport can have no BiDi acknowledgement. Consume that RPC
    // immediately, including late errors during the owner's normal browser.close.
    // Preserve the native density by leaving public DPR emulation unset.
    // Explicitly repeating5/3 becomes1.6666666269302368 in stock Firefox;
    // independent exact native-density readback remains mandatory.
    void Promise.resolve().then(() => {if (deadline-Date.now() <= 0) throw expiry();return page.setViewport({width:expected.width,height:expected.height});}).then(
        () => {acknowledgement='fulfilled';},
        error => {
            const timeout = error?.name === 'TimeoutError' || (error?.name === 'ProtocolError'
                && typeof error.message === 'string' && error.message.startsWith('browsingContext.setViewport timed out.'));
            acknowledgement=timeout?'timed-out':'rejected';
            if (!timeout) {observedFailure=error;rejectFailure(error);}
        });
    let finished = false, effectHandle;
    try {
        await bounded(() => {
            const effect = Promise.resolve().then(() => {if (deadline-Date.now() <= 0) throw expiry();return page.waitForFunction(size => innerWidth === size.width && innerHeight === size.height && devicePixelRatio === size.density,
                {timeout:deadline-Date.now()},expected);}).then(handle => {
                    if (finished) {void Promise.resolve().then(() => handle?.dispose()).catch(() => {});return;}
                    effectHandle=handle;return handle;
                });
            return Promise.race([effect,failure]);
        });
        if (observedFailure) throw observedFailure;
        const accepted = await admit('public-viewport-effect',acknowledgement);
        if (observedFailure) throw observedFailure;
        accepted.viewportAcknowledgementAtReturn=acknowledgement;
        return accepted;
    } finally {
        finished=true;
        if (effectHandle) await Promise.resolve().then(() => effectHandle.dispose()).catch(() => {});
        effectHandle=undefined;
    }
}

function pageAdapter(page) {
    let querySequence = 0;
    const locator = selector => {
        const evaluate = async (callback, ...args) => {
            const handle = await page.locator(selector).waitHandle();
            try { return await handle.evaluate(callback, ...args); }
            finally { await handle.dispose(); }
        };
        return {
            fill: value => page.locator(selector).fill(value),
            click: options => page.locator(selector).click(options),
            evaluate,
            boundingBox: () => evaluate(element => {
                const rect = element.getBoundingClientRect();
                return element.getClientRects().length ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null;
            }),
            waitFor: ({ state = 'visible', timeout = 30000 } = {}) => page.waitForFunction((selector, state) => {
                const element = document.querySelector(selector);
                const visible = !!element && !!element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
                return state === 'visible' ? visible : state === 'hidden' ? !visible : state === 'attached' ? !!element : !element;
            }, { timeout }, selector, state),
            innerText: () => evaluate(element => element.innerText),
            textContent: () => evaluate(element => element.textContent),
        };
    };
    return {
        on: (event, callback) => { page.on(event, callback); },
        bringToFront: () => page.bringToFront(),
        addInitScript: (callback, ...args) => page.evaluateOnNewDocument(callback, ...args),
        goto: (url, options) => page.goto(url, options),
        evaluate: (callback, ...args) => page.evaluate(callback, ...args),
        waitForFunction: (callback, arg, options = {}) => page.waitForFunction(callback, options, arg),
        locator,
        getByLabel: label => locator(`[aria-label=${JSON.stringify(label)}]`),
        getByRole: (role, { name, exact = false } = {}) => {
            const selector = `[data-overte-bidi-query="${++querySequence}"]`, marker = String(querySequence);
            const resolve = async () => {
                await page.waitForFunction((role, name, exact, marker) => {
                    const selectors = { button: 'button,[role="button"]', link: 'a[href],[role="link"]' };
                    if (!selectors[role]) throw Error('Unsupported actual-journey role');
                    const element = Array.from(document.querySelectorAll(selectors[role])).find(element => {
                        const text = (element.getAttribute('aria-label') || element.textContent || '').trim();
                        return element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden' && (name === undefined || (exact ? text === name : text.includes(name)));
                    });
                    if (!element) return false;
                    element.setAttribute('data-overte-bidi-query', marker); return true;
                }, { timeout: 30000 }, role, name, exact, marker);
                return locator(selector);
            };
            return {
                click: async options => (await resolve()).click(options),
                evaluate: async (callback, ...args) => (await resolve()).evaluate(callback, ...args),
                boundingBox: async () => (await resolve()).boundingBox(),
            };
        },
        keyboard: {
            down: key => page.keyboard.down(key),
            up: key => page.keyboard.up(key),
            press: async (key, options) => {
                const parts=key.split('+');if(parts.length===1)return page.keyboard.press(key,options);
                const modifiers=parts.slice(0,-1);if(modifiers.some(value=>!['Control','Alt','Meta','Shift'].includes(value)))throw Error('Unsupported actual-journey key modifier');
                const held=[];
                try{for(const modifier of modifiers){await page.keyboard.down(modifier);held.push(modifier);}await page.keyboard.press(parts.at(-1),options);}
                finally{for(const modifier of held.reverse())await page.keyboard.up(modifier);}
            },
        },
        mouse: page.mouse,
        screenshot: async ({ animations, caret, ...options }) => {
            // Apply the journey's screenshot-only CSS settings; retain every actual WebGL world pixel.
            const style = animations === 'disabled' || caret === 'hide'
                ? await page.addStyleTag({ content: `${animations === 'disabled' ? '*{animation:none!important;transition:none!important;}' : ''}${caret === 'hide' ? '*{caret-color:transparent!important;}' : ''}` }) : undefined;
            try { return await page.screenshot(options); }
            finally { if (style) { await style.evaluate(element => element.remove()); await style.dispose(); } }
        },
    };
}

/** Return only the Playwright-compatible methods used by real-session.mjs; no assertions are substituted. */
export async function launchSystemFirefox({ executablePath = '/usr/bin/firefox', env = process.env, headless = true, syntheticMicrophone = true } = {}) {
    if (typeof syntheticMicrophone !== 'boolean') throw Error('syntheticMicrophone must be an explicit boolean.');
    const browser = await puppeteer.launch({
        browser: 'firefox', protocol: 'webDriverBiDi', executablePath, headless, env,
        ...(headless ? {} : {defaultViewport:null}),
        extraPrefsFirefox: {
            'media.navigator.streams.fake': syntheticMicrophone,
            'media.navigator.permission.disabled': true,
        },
    });
    const version = await browser.version();
    return {
        version: () => version,
        newContext: async ({ viewport = { width: 1280, height: 800 }, permissions = [] } = {}) => {
            if (permissions.length) throw Error('The stock Firefox journey uses its explicit fake-media preferences, not unrelated permission overrides.');
            const context = await browser.createBrowserContext();
            return {
                newPage: async () => {
                    const page = await context.newPage();
                    if (headless) await page.setViewport(viewport);
                    else await sizeSystemFirefoxWindow(browser, page, viewport);
                    return pageAdapter(page);
                },
                close: () => context.close(),
            };
        },
        close: () => browser.close(),
    };
}
