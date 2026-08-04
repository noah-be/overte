# Pico 4 power-test reports

This directory contains the reviewed, committed reports from Pico 4 power
experiments:

- [Fan duty](fan-power.md)
- [Display brightness](display-brightness-power.md)
- [Overte Hub baseline at 100% display and fan](overte-hub-baseline.md)
- [Experimental bundled Pico power profile](pico-power-profile.md)
- [Pico 4 graphics optimization](pico-graphics-optimization.md)

The test procedure and recorder usage are documented in
[PICO4_POWER_TEST.md](../../PICO4_POWER_TEST.md). Raw CSV recordings remain in
the Git-ignored `android/power-results/` directory and are not committed.

For bounded CPU hot-path recording, `pico-simpleperf.sh` prepares and verifies
the same Hub scene, records the debuggable app through `simpleperf --app`, and
produces command-, library-, and symbol-sorted reports without taking a
screenshot. Its default 99 Hz leaf sampling avoids the multi-gigabyte temporary
stack data produced by Android simpleperf's 4000 Hz DWARF default. A watchdog
checks the resumed activity, Pico Guardian state, process identity, and (for a
prepared run) Hub domain before, during, and after recording; it rejects the
profile instead of publishing measurements after XR focus, process, or scene
validity has been lost. Run:

```bash
cd android
./pico-simpleperf.sh
```

Use `--call-graph fp` only when a call graph is required and the current build
has usable frame pointers. In this mode the recorder also writes
`report-callgraph-children.txt`, whose `Children` column attributes samples to
every parent in a captured call chain instead of only to the sampled leaf.
Results are written below the Git-ignored `android/power-results/` directory.
`--binary-cache` additionally resolves the record against unstripped native
build outputs, but is opt-in because a full cache can require several
gigabytes.

The Pico test scripts use `PICO_SERIAL` or `ANDROID_SERIAL` when set. Without
either variable they require exactly one authorized device in `adb devices`
and select it automatically. No developer-specific device address or serial
number is stored in the repository or result metadata.

The graphics matrix applies XR-focus, process-identity, and authoritative Hub
world/domain checks around scene capture and each telemetry sample. This
complements image similarity and prevents a boundary dialog, restarted
process, disconnect, or domain change from being accepted as a low-load scene.
Missing or malformed process-CPU samples also invalidate the case instead of
entering an empty CSV value.

For local avatar-load screening, first enter a domain containing at least one
other avatar, then create up to 50 client-only copies per received avatar:

```bash
cd android
./pico-unattended-test.sh replicas 5
./pico-unattended-test.sh avatar-status
./pico-unattended-test.sh replicas 0
```

The status reports total and locally replicated avatar counts, the existing
avatar update-budget counters, and the mean avatar-simulation time across all
frames in the latest one-second status interval. Replica commands are
timestamped and ignored when stale, so an interrupted test cannot replay its
load after a later app restart. Test mode itself is re-read at runtime. Always
return the count to zero after a test.

In test mode, the status also breaks total other-avatar processing into
priority-queue construction, sorting, pre-update state work, scene assurance,
scale animation, and the budgeted simulation/render-update section. These are
wall-clock timings and can include time while Android deschedules the main
thread; use a CPU profile before treating a large stage as compute work. When
no other avatar exists, all timings and update counters reset to zero. The
matrix rejects an old, incomplete, non-numeric, or internally inconsistent
timing/counter schema instead of silently shifting or coercing CSV columns.

For a guarded repeated A/B matrix in the current domain, run:

```bash
./pico-avatar-matrix.sh
```

The default sequence is 0, 5, 0, and 5 copies per real template avatar.
Repeated `--replicas` options define a different sequence. The matrix fixes the
fan and brightness during measurement, rejects XR-focus loss or any change in
the real template population, disconnect, or starting domain, enables test
mode for the run, writes aggregate CSV results under `android/power-results/`,
then clears all copies and restores test mode and the device controls. An app
restart also rejects the run rather than mixing measurements from different
processes. It never records screenshots, avatar identifiers, or the checked
domain ID. The summary includes mean updated and budget-skipped avatar counts,
so CPU stability is not mistaken for full crowd simulation quality. Here,
`updated` counts in-view avatars with fresh joint data while the update is
within budget; it is not a count of every simulated avatar. `aggregate.csv`
combines repeated stages with the same replica count.

Both matrix tools create an `INVALID` marker before collecting a matrix or
graphics case and remove it only after all required validation and output
steps complete. Partial diagnostic files are retained after an abort, but a
consumer can reject them without interpreting CSV or image contents.

Avatar matrices, graphics matrices, and simpleperf recordings refuse a
non-empty result directory. This prevents a retry or mistyped path from
overwriting a prior valid run or combining artifacts from different runs.
