// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vite';

export default defineConfig({
    server: { host: '127.0.0.1', port: 5187, strictPort: true },
    preview: { host: '127.0.0.1', port: 4187, strictPort: true },
    worker: { format: 'es' },
    build: { target: 'es2022', sourcemap: true },
});
