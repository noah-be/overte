// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
// @ts-expect-error Production JavaScript helper intentionally has no generated declaration file.
import { ASSET_SANDBOX_POLICY } from '../gateway/validation.mjs';

let server: Server, endpoint: string;
test.beforeAll(async () => {
    server = createServer((request, response) => {
        if (request.url === '/image.svg') {
            response.writeHead(200, { 'content-type': 'image/svg+xml', 'content-security-policy': ASSET_SANDBOX_POLICY });
            response.end('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="red"/></svg>');
        } else if (request.url === '/document') {
            response.writeHead(200, { 'content-type': 'text/html', 'content-security-policy': ASSET_SANDBOX_POLICY });
            response.end('<title>Safe asset</title><script>window.assetScriptRan=true;document.title="Compromised gateway";</script>');
        } else {
            response.writeHead(200, { 'content-type': 'text/html' });
            response.end('<title>Texture host</title><img src="/image.svg" alt="Asset texture">');
        }
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    endpoint = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
test.afterAll(async () => { await new Promise<void>(resolve => server.close(() => resolve())); });

test('asset policy blocks same-origin document script while allowing texture decoding', async ({ page }) => {
    await page.goto(`${endpoint}/document`);
    await expect(page).toHaveTitle('Safe asset');
    expect(await page.evaluate(() => (window as unknown as {assetScriptRan?: boolean}).assetScriptRan)).toBeUndefined();
    expect(await page.evaluate(() => window.origin)).toBe('null');
    await page.goto(`${endpoint}/`);
    await expect.poll(() => page.locator('img').evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(16);
});
