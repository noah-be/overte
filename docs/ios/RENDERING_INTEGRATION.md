# Native iOS rendering integration audit

[`ios/rendering-integration-inventory.json`](../../ios/rendering-integration-inventory.json) records the source-backed path from `entities-renderer` through the existing GPU abstraction to Vulkan, MoltenVK, and a Metal-backed swapchain. It is an audit of the real renderer and does not treat bootstrap Metal geometry as evidence.

Run the drift validator on any host:

```sh
python3 ios/tests/rendering-integration-inventory-test.py
```

MoltenVK discovery, static linkage, `VK_USE_PLATFORM_METAL_EXT`, and the `vkCreateMetalSurfaceEXT` implementation are present. The iOS full-client graph now defaults to Vulkan and rejects any other backend; the earlier bootstrap-only return remains unaffected. `VKWindow::createSurface()` has an iOS-only Objective-C++ bridge that obtains Qt's native `CAMetalLayer`; Windows and X11 retain their existing branches. `display-plugins` also skips its redundant direct `target_opengl()` invocation only for iOS with the Vulkan backend; desktop, non-Vulkan, and Android behavior remains unchanged.

The former Qt `GuiPrivate` dependency was caused only by unused `qpa/qplatformnativeinterface.h` includes in `VKWindow.cpp` and `VKWidget.cpp`; all native-interface calls were commented out. Those includes and the unused `QtPlatformHeaders/QXcbWindowFunctions` include are removed, and the X11 header in `VKWindow.cpp` is now restricted to non-Windows, non-iOS builds. The `vk` target therefore links only public Qt Core/Gui APIs. Full iphoneos and iphonesimulator compilation remains the external confirmation that no transitive private-header assumption exists.

## Remaining explicit GL API boundary

Removing `gpu-gl-common/gpu-gl` from backend selection does not yet make Interface or `display-plugins` GL-free. Two explicit `gl` links remain source-required:

- `DisplayPlugin::copyTextureToQuickFramebuffer` now exposes only the backend-neutral `QuickTextureCopyTarget`; Qt OpenGL and GL fence types no longer leak through the public ABI.
- `ResourceImageItem` constructs OpenGL framebuffer objects and waits/deletes GL fences.
- The display-plugin target still compiles the OpenGL, stereo, and HMD source families because its library macro gathers the complete source directory, even though Vulkan is selected at runtime.
- Interface compilation directly includes GL helpers in application, canvas, graphics, statistics, menu, and main paths.
- `VulkanDisplayPlugin.cpp` retains GL context/helper dependencies beyond the now-gated Quick-copy method.

[`ios/rendering-integration-inventory.json`](../../ios/rendering-integration-inventory.json) records five source-anchored migration tasks. The first is complete: the public method takes an opaque framebuffer/completion-token target and reports success explicitly. Existing OpenGL behavior is adapted internally in `OpenGLDisplayPlugin`; iOS/Vulkan clears the token and returns `false`. `ResourceImageItem` still needs a QRhi- or Metal-compatible implementation before its internal framebuffer/fence and the explicit links can be removed.

The iOS platform-backend list now contains only `gpu-vk;vk`; its legacy `gpu-gl-common;gpu-gl` bridge list is empty. This is not a claim that the entire application is GL-free. `interface` and `display-plugins` still link the shared `gl` library explicitly because public plugin APIs expose `QOpenGLFramebufferObject`/`GLsync` and other source paths retain GL-typed helpers. Those explicit dependencies are separate from selecting both OpenGL and Vulkan backend implementations through `PLATFORM_GL_BACKEND`.

The desktop external-texture path depends on GL memory-object imports and `GLsync`; MoltenVK cannot provide equivalent semantics. iOS therefore defines `OVERTE_IOS_VULKAN_DISABLE_EXTERNAL_GL_INTEROP`: external textures return no GPU object with a one-time critical diagnostic, and recycler fence work asserts if it becomes reachable. This is intentionally fail-closed until a native IOSurface/Metal import exists; ordinary entity model/material textures do not use the external-texture contract.

The legacy Quick-copy behavior still cannot be implemented on a Metal-only iOS surface, although its public ABI is now neutral. The Vulkan implementation was already an inactive `#if 0` stub on every platform. iOS makes that state explicit with `OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY`, clears the opaque completion token, returns `false`, and emits one critical diagnostic requesting a QRhi/Metal-native bridge. This affects only `ResourceImageItem`-style Qt Quick image copies, not normal entity or material texture upload and rendering.

The gated external-texture class, its GL helper include, GL-typed backend members, and GLsync cleanup are excluded from iOS compilation. Consequently `gpu-vk` no longer links `gl` directly on iOS; non-iOS builds retain the original link. All source-anchored hybrid-backend migration tasks are complete. Full iphoneos and iphonesimulator configuration/linking remains the honest acceptance gate for transitive dependency or platform-plugin issues, followed by the existing entity render-handoff marker on a device; a standalone Metal preview is insufficient.
