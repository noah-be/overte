// SPDX-License-Identifier: Apache-2.0
import { defineConfig, devices } from '@playwright/test';

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
        {name:'chromium', use:{...devices['Desktop Chrome'], launchOptions:{args:['--use-angle=swiftshader']}}},
        {name:'firefox', use:{...devices['Desktop Firefox'], launchOptions: {
            // CI uses an actual Mesa software context, which Firefox can otherwise blocklist.
            firefoxUserPrefs: process.env.CI ? {'webgl.force-enabled':true} : {},
        }}},
    ],
    webServer: {command:'npm run dev', url:'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI},
});
