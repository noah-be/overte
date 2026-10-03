// SPDX-License-Identifier: Apache-2.0
import { defineConfig, devices } from '@playwright/test';
import {googleChromeLaunchOptions} from './tests/google-chrome-selection.mjs';
const chrome = googleChromeLaunchOptions();

export default defineConfig({
    testDir: './tests',
    testMatch: '*.browser.spec.ts',
    timeout: 45000,
    expect: {timeout:10000},
    fullyParallel: true,
    workers: process.env.CI ? 1 : 2,
    reporter: [['list'], ['html', {open:'never'}]],
    use: {baseURL:'http://127.0.0.1:5173', screenshot:'only-on-failure', trace:'retain-on-failure'},
    projects: [
        // Branded Google Chrome; do not silently fall back to bundled Chromium.
        {name:'google-chrome', use:{...devices['Desktop Chrome'], ...('channel' in chrome?{channel:chrome.channel}:{}), launchOptions:{...('executablePath' in chrome?{executablePath:chrome.executablePath}:{}),args:['--use-angle=swiftshader']}}},
    ],
    webServer: {command:'npm run dev', url:'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI},
});
