// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Preserve the real-domain journey while driving an unpatched installed Firefox over WebDriver BiDi.
// Primary references: https://pptr.dev/api/puppeteer.launchoptions and https://pptr.dev/next/webdriver-bidi
// Fake-media preferences: https://searchfox.org/firefox-main/source/modules/libpref/init/all.js
import puppeteer from 'puppeteer-core';

/** Size the actual headed window, keeping the desktop's native pixel density.
 * Firefox BiDi viewport emulation can time out on fractional-DPI desktops.
 * The public window API plus an exact inner-size assertion avoids emulation.
 */
export async function sizeSystemFirefoxWindow(browser, page, viewport) {
    if (![viewport.width, viewport.height].every(value => Number.isSafeInteger(value) && value > 0)) throw Error('Invalid actual Firefox window dimensions.');
    const windowID = await page.windowId();
    await browser.setWindowBounds(windowID, {windowState:'normal'});
    const bounds = await browser.getWindowBounds(windowID);
    const inner = await page.evaluate(() => ({width:innerWidth,height:innerHeight}));
    await browser.setWindowBounds(windowID, {windowState:'normal',
        width:viewport.width+bounds.width-inner.width, height:viewport.height+bounds.height-inner.height});
    await page.waitForFunction(size => innerWidth === size.width && innerHeight === size.height, {timeout:10000}, viewport);
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
