# iPad render diagnostics without rebuilding

The physical-device build reads `Documents/overte-ios-render-diagnostics.json`
and notices valid file replacements. Replace that file through House
Arrest/AFC while the app is closed, then launch Overte again. Reinstalling,
resigning, rebuilding, and rebooting the iPad are not required. Settings that
control construction of Vulkan resources take effect for newly created
resources, so restart the app after changing them.

The first `OVERTE_IOS_VULKAN_CONFIG` line proves which file and settings were
loaded. `file_exists=1`, a non-zero `json_keys`, and the requested selectors
must be visible before treating a run as valid.

Start with `render-diagnostic-profiles/normal-trace.json`. The supplied profiles
can then isolate the already identified particle DrawCallInfo path, translucent
model/light-cluster path, and forward skybox path. A custom profile can select:

- complete batches by stable batch name or `batch:<fingerprint>`;
- shaders by vertex name, fragment name, or `vertex|fragment` pair;
- one stable `pipeline:<fingerprint>`;
- draw command type, named call, or `BatchName#commandIndex`;
- every draw after a global ordinal by setting `executeDrawOrdinalLimit`;
- uniform/storage bindings replaced with a zero buffer;
- texture bindings or exact texture sources replaced with a valid fallback;
- bounded detailed tracing for a batch, shader, pair, or named call.

`OVERTE_IOS_VULKAN_PIPELINE_USE` reports all selector values and the global
ordinal. `OVERTE_IOS_VULKAN_DRAW_BUFFER`, `DRAW_ACCESS`, `INPUT_ACCESS`,
`DESCRIPTOR`, and `TEXTURE` report the corresponding CPU-visible ranges.
Invalid DrawCallInfo, transform-object, index, vertex, and descriptor ranges
are emitted as fault-level records even outside the detailed trace window.

Automatic submit-candidate persistence remains useful after a GPU reset. Set
`ignorePersistedQuarantine` for an A/B run without changing CFPreferences, or
set `clearPersistedQuarantine` for one launch to remove it. Set
`persistSubmitCandidates` to false while running deliberate isolation profiles.

Light-cluster bindings 10, 11, and 12 are listed in the supplied light-cluster
profile. Replacing them with zero buffers leaves the binary unchanged while
testing whether a remaining physical-device fault is in clustered lighting.

## Physical-device texture memory

Ordinary downloaded world textures use the reliable strict Vulkan upload path
but are capped on iOS before upload. `iosResourceTextureMaxDimension` accepts
64 through 16384 and defaults to 512. Use 256 for a low-memory isolation run,
512 for the safe default, or 1024 to compare quality after memory headroom has
been proven. Restart Overte after changing the value; no new IPA is needed.
Strict UI and special-purpose textures are not reduced.

`OVERTE_IOS_TEXTURE_MEMORY` records live Vulkan texture count/bytes, the
process physical footprint used by Jetsam, original and uploaded dimensions,
and the selected source mip. `iosTextureTraceEvery` controls the interval for
these bounded records and defaults to every 64 creations.
