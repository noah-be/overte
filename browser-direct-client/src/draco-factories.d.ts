// SPDX-License-Identifier: Apache-2.0
// The two pinned Google factory files expose Emscripten's dynamic native API.
declare module 'draco3d/draco_decoder_nodejs.js' {
  const create: (options: Record<string, unknown>) => any;
  export default create;
}
declare module 'three/examples/jsm/libs/draco/draco_wasm_wrapper.js' {
  const create: (options: Record<string, unknown>) => Promise<any>;
  export default create;
}
