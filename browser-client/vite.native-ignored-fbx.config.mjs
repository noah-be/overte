// SPDX-License-Identifier: Apache-2.0
export default {base:'./',build:{outDir:'build-native-ignored-fbx',lib:{entry:'tests/fixtures/native-ignored-fbx-pixels.ts',formats:['es'],fileName:'entry'},rollupOptions:{output:{assetFileNames:'assets/[name]-[hash][extname]'}}},worker:{format:'es'}};
