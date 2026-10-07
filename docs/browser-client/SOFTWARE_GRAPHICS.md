<!-- SPDX-License-Identifier: Apache-2.0 -->
# Software graphics for browser verification

The native-ignored FBX pixel control and actual Core journey request ANGLE
SwiftShader when `LIBGL_ALWAYS_SOFTWARE=true`, including beneath Xvfb. A virtual
display by itself does not select Chrome's software backend. The Core journey
also retains its existing SwiftShader request in headless mode.

The launchers share `browser-client/tests/software-graphics.mjs`. They retain
branded Google Chrome selection, audio flags, all journey actions, deadlines,
pixel comparisons, GL-error assertions, and native permission boundaries. No
context-loss retry or WebGL-error suppression is added. Ordinary headed runs
without the explicit software setting retain Chrome's default backend.

Run the focused launch-contract regression with:

```sh
cd browser-client
node --test tests/software-graphics.test.mjs
```

Then run the normal Browser workflow. The software launch contract and a local
software-rendered fixture do not establish native movement, voice, reconnect,
physical-device or public-world acceptance. Those results require their actual
source-bound journeys.

The V31 capture source manifest records this migration while preserving the
V30 manifest and historical assertion bodies. Production preparation accepts
the exact V31 manifest and current files; historical normalization is confined
to CPU tests and is not an acceptance fallback.
