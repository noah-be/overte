# iPad render diagnostics without rebuilding

The physical-device build reads `Documents/overte-ios-render-diagnostics.json`
once at process startup. Replace that file through House Arrest/AFC while the
app is closed, then launch Overte again. Reinstalling, resigning, rebuilding,
and rebooting the iPad are not required.

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
