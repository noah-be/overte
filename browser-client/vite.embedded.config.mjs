// SPDX-License-Identifier: Apache-2.0
import {defineConfig} from 'vite';
export default defineConfig({build:{outDir:'build-embedded',emptyOutDir:true,lib:{entry:'tests/fixtures/embedded-worker-entry.ts',formats:['es'],fileName:'entry'},minify:false},worker:{format:'es'}});
