// SPDX-License-Identifier: Apache-2.0
// Isolated short Chrome-only qualification; inherited launch and timeout gates.
import {defineConfig} from '@playwright/test';
import original from './playwright.config';
export default defineConfig({...original,testMatch:'world-image-approval.browser.spec.ts',fullyParallel:false,workers:1});
