// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Preserve the real-domain journey while driving an unpatched installed Firefox over WebDriver BiDi.
// Primary references: https://pptr.dev/api/puppeteer.launchoptions and https://pptr.dev/next/webdriver-bidi
// Fake-media preferences: https://searchfox.org/firefox-main/source/modules/libpref/init/all.js
import puppeteer from 'puppeteer-core';

function pageAdapter(page) {
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
            innerText: () => evaluate(element => element.innerText),
            textContent: () => evaluate(element => element.textContent),
        };
    };
    return {
        on: (event, callback) => { page.on(event, callback); },
        addInitScript: (callback, ...args) => page.evaluateOnNewDocument(callback, ...args),
        goto: (url, options) => page.goto(url, options),
        evaluate: (callback, ...args) => page.evaluate(callback, ...args),
        waitForFunction: (callback, arg, options = {}) => page.waitForFunction(callback, options, arg),
        locator,
        keyboard: page.keyboard,
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
                    await page.setViewport(viewport);
                    return pageAdapter(page);
                },
                close: () => context.close(),
            };
        },
        close: () => browser.close(),
    };
}
