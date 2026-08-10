# Android Phone world-loading performance tests

This harness measures the regular `org.overte.phone` Android client on a
physical, non-VR phone. It does not run the Pico client and rejects known Pico,
VR, emulator, TV, watch, and automotive targets. It also uses the repository's
exclusive Phone device lock, so it cannot overlap another managed device run.

## Run a test

Install a debuggable Phone APK, connect one phone with ADB, and choose an online
world that is stable enough for comparisons:

```bash
cd android
ANDROID_SERIAL=<serial> PHONE_PERF_CONFIRM_NON_VR=YES \
  ./tests/phone-world-loading-test.sh \
  --target overte://<domain-or-place>/<x>,<y>,<z> \
  --runs 5 --duration 90 --warmup 5 \
  --output-dir /tmp/overte-phone-baseline
```

The target must use `overte://` or `hifi://` and end in an explicit `/X,Y,Z`
spawn position. This prevents a benchmark from silently changing to the
world's default spawn. The launcher receives the complete URL through
the same browsable deep-link path as a user opening a world link. Each run first
starts the client and explicitly navigates it to the packaged
`file:///~/serverless/tutorial.json`, independent of a remembered location or
home bookmark. After the configured warm-up, the harness resets its baselines,
starts recording, and only afterwards sends the target deep link. The recorded
interval therefore covers the deterministic warm-client transition from the
local tutorial into the requested online world.

Some worlds apply their own default spawn after the deep link has already been
accepted. During a test the harness detects a connected client more than five
metres from the requested coordinates and uses the test-only teleport property
to restore the explicit position. Both the pre-correction and corrected values
remain in `world-status.csv`; the final analyzer check still fails unless the
client ends at the requested spawn.

Use `--cold-cache` to remove only `org.overte.phone`'s cache before each run.
This requires a debuggable APK but preserves account and preferences. Use
`--perfetto` to add a system trace for CPU scheduling, frequencies, graphics,
Binder, window/activity management, and power events.
Use `--brightness 128` to disable automatic brightness for the run, apply a
repeatable mid-level setting, and restore both original display settings when
the harness exits, including after failures.
`--allocator-decay 0` is a diagnostic mode that asks Android's allocator to
release unused pages immediately; `1` selects its device-specific interval.

## Results

`runs.csv` contains per-run aggregates. Each `run-N` directory contains:

- one-second CPU, detailed PSS/RSS/swap memory and app-UID network samples;
- five-second thermal status, CPU/GPU/battery/skin temperatures, battery
  current/voltage/charge, explicit AC/USB/wireless/dock power source, charging
  state and advertised maximum charging current/voltage, Wi-Fi radio metrics, configured screen brightness,
  automatic-brightness mode, and actual display brightness;
- Android `gfxinfo` frame statistics;
- native Phone renderer FPS, inter-present timing, GPU/batch timing and texture
  memory parsed from `OvertePhoneGraphics` telemetry;
- final `meminfo`, launch timing, and continuously streamed process Logcat;
- an optional Perfetto trace.
- `final-overte-hub.png`, captured after the measured interval and before the
  harness stops the app.
- `world-status.csv`, containing the client-reported connection flag, Place,
  Domain ID, avatar position, resource queues, and GPU memory for every sample.
- `memory-detail.csv`, containing a non-GC-inducing ten-second breakdown of
  Dalvik, native allocator, graphics, stack, library, code, file and anonymous
  PSS together with thread, file-descriptor and on-disk cache counts.
- `memory-mappings.csv`, retaining every mapping of at least 1 MiB at each
  detail interval so anonymous arena and non-allocator growth can be compared.
- `script-memory.csv`, containing per-script V8 total/used heap, available
  address space and global-handle memory emitted asynchronously by each script
  thread without blocking the application thread.

`summary.txt` reports per-run values and medians. Network counters are read from
Android's per-UID kernel accounting, with `dumpsys netstats` as the fallback on
newer Android versions that restrict the legacy kernel files. A device exposing
neither source records zero, which remains visible in the raw samples. GPU
frequency/temperature exposure is also vendor-dependent.

For measurements of at least five minutes, the analyzer additionally prints
five-minute phases with mean CPU, PSS delta and regression slope, network
traffic, and peak CPU/GPU temperature. Multi-run summaries include relative
spread so an unstable public-world sample is visible rather than hidden by its
median.

World status analysis reports elapsed time to the first domain connection, the
first correct spawn sample, the first empty resource queue, and the start of
the final uninterrupted empty-queue interval. The last value is the most useful
automated approximation of completed world loading.

At the end of every run, the harness inspects the visible Android UI for a
domain-connection failure dialog. Such a run remains available for diagnosis
but is marked with `connection_error_dialog=1` and makes the analyzer fail.
It also captures the final screen and requires a readable, non-black PNG.
`screenshot_valid=0` fails the run. The retained image provides the visual
control that the expected Hub spawn was still rendered before cleanup. The
PNG validity check is automatic; recognizing a particular 3D spawn remains a
visual review unless a reviewed scene-specific reference image is supplied in
the future. Do not treat `screenshot_valid=1` alone as semantic proof that the
correct world finished loading.

The analyzer also requires the final active and pending resource-download
queues to be empty. This prevents a visually recognizable but still explicitly
`LOADING CONTENT` frame from being accepted as a completed world load.

Android HWUI `gfxinfo` does not necessarily cover the native Qt/OpenGL surface.
Its jank percentage is retained as raw platform evidence, but native
`OvertePhoneGraphics` present FPS and timing are authoritative for this client.

`--duration` is wall-clock time, not a requested sample count. CPU and memory
are sampled on an approximately one-second cadence. More expensive network,
thermal, battery, and temperature queries are refreshed every five seconds and
carried forward between refreshes so they do not distort the loading timeline.
The accepted duration range is 5–7200 seconds, supporting bounded one- and
two-hour soak tests.

Keep these variables fixed when comparing commits: phone model and OS build,
world, Wi-Fi network, screen brightness, duration, cache mode, initial battery
and thermal state, and whether/how the device is charging. Run cold-cache and
warm-cache series separately. Start
threshold enforcement only after collecting a stable device-specific baseline.

### Provisional Pixel 8 Pro / public overte_hub gates

The 2026-08-10 baseline used Android's fixed brightness value 128, automatic
brightness off, Wi-Fi ADB, the public `overte_hub` spawn
`154.69,-98.296,-397.899`, and Perfetto. These are investigation gates, not
portable product requirements. The post-OpenEXR reference series was measured
while AC powered; do not compare it directly with an unplugged run:

| Profile | Regression gate |
| --- | --- |
| Warm cache, 5 min, at least 2 runs, AC powered | all correctness checks pass; sustained queue idle <= 90 s; median native present FPS >= 28; median mean CPU <= 350%; median peak PSS <= 1100 MiB; median download <= 70 MiB; median GPU frame time <= 15 ms |
| Cold cache, 5 min, at least 3 runs, AC powered | all correctness checks pass; median sustained queue idle <= 300 s; median mean CPU <= 600%; median peak PSS <= 1300 MiB; median download <= 150 MiB; median GPU frame time <= 15 ms |

The generous cold thresholds include observed variance in the mutable public
world. Tighten them only after a pinned benchmark world is available. Treat a
single failure as diagnostic and require a repeated failure before calling it a
performance regression; correctness failures always invalidate the run.

The current optimization target is the cold loading phase: the post-OpenEXR
three-run series downloaded 125.0–126.0 MiB, reached 1146–1166 MiB peak PSS,
and needed 169–259 seconds before the resource queue stayed empty.
Mapping and heap-profile evidence attributes this primarily to resource loading,
FBX/animation processing and anonymous native high-water memory, while V8 heaps,
thread counts and file descriptors do not show a repeatable leak. Optimize or
deduplicate those resource paths before changing allocator policy. The public
Hub also serves EXR sky/ambient assets. Android builds must retain the
repository's OpenEXR dependency and decoder; the analyzer rejects the former
`Invalid Format` failure because it produced white/black sky regions and made
visual comparisons misleading.

## Scope and interpretation

This initial harness deliberately uses Android system metrics so it works with
existing Phone debug builds. `am_total_ms` is Activity launch time, not world
completion time. Client-reported connection, spawn, entity/resource state and
queue-idle milestones identify the expensive loading interval and transition to
steady state. A precise first-playable-frame marker is still unavailable and is
not silently inferred from CPU, network traffic, or an empty resource queue.
