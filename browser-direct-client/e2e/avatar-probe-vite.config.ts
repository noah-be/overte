// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { fileURLToPath } from 'node:url';
import { defineConfig, mergeConfig } from 'vite';
import production from '../vite.config.ts';

export default mergeConfig(production, defineConfig({
    build: { rolldownOptions: { input: fileURLToPath(new URL('./avatar-probe.html', import.meta.url)) } },
}));
