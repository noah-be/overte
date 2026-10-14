# iOS graphics preferences and startup defaults

The normal graphics page remains the generic shared page. On iOS, its saved
render mode, haze, shadows, bloom, ambient occlusion, anti-aliasing, resolution
scale, world detail,
refresh-rate profile and custom Focus Active/Inactive/Startup rates now survive
normal startup. The application captures the saved values before Render loads
its settings or the performance preset writes defaults, then restores that
choice through the existing native setters. This also preserves a saved scale
through the existing first-use resolution migration. Other custom regimes are
untouched.

Unset values retain the established mobile baseline: effects off, no AA,
resolution scale 0.8, low world detail, custom active/inactive/startup rates of
30 Hz. An existing laboratory profile with those choices stays identical.
Invalid scale/profile input falls back to a valid/default choice; the captured
detail choice uses the existing enum range. A 30 Hz startup baseline or 0.8 scale default is not a proven permanent
hardware maximum and no longer silently replaces a later saved user choice.

The unchanged NativeMetrics frame policy still transiently caps the effective
rate to 30 when current native thermal data is unavailable, serious, or low
power, and to 15 when critical. Nominal valid native data admits the requested
rate. These runtime limits do not rewrite preferences. Actual display limits,
framebuffer allocation, GPU effects and thermals still need native observation.

The mandatory `ios/tests/run-tests.sh` includes:

```bash
python3 ios/tests/native_contracts/test_graphics_preferences.py
```

It compiles the actual application startup, Render load/set/force methods,
performance-preset setup/application, explicit preset choices, LOD setters/storage, Settings value getter
and refresh setters. A real Qt INI store survives separate processes. Tests
cover first/repeated starts, changed user choices and further changes, partial
preferences, unknown-preset reassignment, first resolution migration, all custom
regimes and the previous c41 destructive behavior. The original native thermal
policy is executed as well. GPU/platform/display objects and the asynchronous
Setting::Manager worker are explicit fixture boundaries. This is neither a
complete Apple SDK compile nor physical iPad evidence.

The shared touch default script still unconditionally changes automatic LOD
and its angle. That separate Main-owned caller correction is not introduced
through this iOS patch. Full graphics parity remains open until that normal
parent flow and the real controlled lights/haze/procedural/mirror and persistent
UI journeys are qualified on an exact installed product artifact (#1171).
