<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS rendering spike

The bootstrap application contains a native Metal reference pipeline. It draws
one triangle through `MTKView` and therefore validates the app's CAMetalLayer,
compiled Metal library, command queue, render pass, presentation, rotation, and
iPhone/iPad drawable resizing without involving Qt or Overte's renderer.

The first integrated path evaluates Overte's existing Vulkan backend through a
static MoltenVK XCFramework. Configure it explicitly:

```bash
export OVERTE_IOS_MOLTENVK_ROOT=/absolute/path/to/MoltenVK
./ios/build-ios.sh doctor --platform simulator --require-moltenvk
./ios/build-ios.sh deps --platform simulator --graphics-toolchain
```

The repository never searches a global Vulkan installation for an iOS build.
Device and simulator slices are selected independently.

## Reference workload

The comparison workload contains:

- the native bootstrap triangle;
- a representative Overte world with opaque, transparent, skinned, and
  emissive objects;
- avatar rendering and text;
- texture upload, mip generation, and render-target resizing; and
- ten minutes of continuous camera motion.

Capture GPU frame time, CPU frame time, peak resident memory, dropped frames,
pipeline compilation errors, validation errors, and thermal state on the same
device and OS version.

## Decision rule

MoltenVK becomes the first client backend only if it:

1. produces correct reference frames without an OpenGL dependency;
2. supports every required texture, synchronization, and shader operation;
3. has no persistent validation errors;
4. stays within 15 percent of the native reference's presentation overhead;
5. remains inside the initial memory budget; and
6. passes a 30-minute physical-device stability run.

If any correctness gate fails, implementation switches to a native Metal
backend behind the existing GPU abstraction. Performance alone does not permit
shipping incorrect frames.
