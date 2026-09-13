# Phone loading / ETC regression measurement

The Phone source-only dependency profile intentionally keeps most dependencies in Debug.
The runtime ETC encoder is CPU-intensive: on the Pixel 8 Pro, the original unoptimized
`etc2comp` dependency consumed about 90% of measured raw-texture processing time while
completed downloads accumulated behind two worker jobs. Build only this dependency as
RelWithDebInfo (`-O2 -g -DNDEBUG`), retaining symbols and the pinned recipe/source revision.
This does not change texture resolution, compression effort, format or worker concurrency.
The source-graph manifest binds the updated profile digest.

`etc-benchmark.cpp` calls the production encoder on deterministic 256/512-pixel RGBA
inputs with the application's effort (1), four encode threads and full mip chains.
Build the same benchmark twice against the old and new **arm64 Android** static ETC
archives, using the same NDK compiler and headers. Run both on the same device in ABBA
order with the app stopped. Record elapsed time, thermal conditions, output byte count,
encoded hash and decoded error per pixel. Different encoded hashes need quality review;
they do not alone imply corruption. Do not compare differently optimized benchmark drivers.

The opt-in native records are enabled by Android property `debug.overte.loading=1` before
process start. They include numeric connection/place checks, queue counts, HTTP cache
counters, image/model timings and ETC timings. Regular sessions leave the property unset.
They do not provide a general JavaScript console. The aggregate state uses the existing
10-second telemetry timer; individual jobs record completion times. Zero pending GPU bytes
and empty download queues are insufficient to claim a fully visible, usable world.

For reproducible derived-cache comparisons, set `debug.overte.loading.cache_run` to a
single digit 1–9 before process start while diagnostics are enabled. This uses a separate
KTX directory; it never clears the user's normal cache. Use a previously unused number
for each cold variant and the same number for its warm repeat. Keep downloaded-source
caches, world, avatar, view, Wi-Fi and prelude identical as far as possible. Clear the
property (or set it to 0) and disable diagnostics after measurements to return to the
normal cache. Compare screenshots and touch response in addition to queues/timings.

Local 2026-09-13 evidence and complete harness:
`/home/user/Documents/overte-phone-loading-20260913/TEST_PROTOCOL.md`.
Raw device diagnostics stay in that directory's private subfolder, not in Git.
