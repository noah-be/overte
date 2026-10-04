// SPDX-License-Identifier: Apache-2.0
export default {base:'./',build:{outDir:'build-embedded-world',lib:{entry:'tests/fixtures/embedded-world.ts',formats:['es'],fileName:'entry'},rollupOptions:{output:{assetFileNames:'assets/[name]-[hash][extname]'}}},worker:{format:'es'}};
