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
checks the resumed activity and Pico Guardian state before, during, and after
recording; it rejects the profile instead of publishing measurements taken
after Overte has lost XR focus. Run:

```bash
cd android
./pico-simpleperf.sh
```

Use `--call-graph fp` only when a call graph is required and the current build
has usable frame pointers. Results are written below the Git-ignored
`android/power-results/` directory. `--binary-cache` additionally resolves the
record against unstripped native build outputs, but is opt-in because a full
cache can require several gigabytes.

The graphics matrix applies the same XR-focus checks around scene capture and
each telemetry sample. This complements image similarity and prevents a
boundary dialog from being accepted as a low-load scene.

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
no other avatar exists, all timings and update counters reset to zero.

For a guarded repeated A/B matrix in the current domain, run:

```bash
./pico-avatar-matrix.sh
```

The default sequence is 0, 5, 0, and 5 copies per real template avatar.
Repeated `--replicas` options define a different sequence. The matrix fixes the
fan and brightness during measurement, rejects XR-focus loss or any change in
the real template population, enables test mode for the run, writes aggregate
CSV results under `android/power-results/`, then clears all copies and restores
test mode and the device controls. An app restart also rejects the run rather
than mixing measurements from different processes. It never records
screenshots or avatar identifiers. The summary includes mean updated and
budget-skipped avatar counts, so CPU stability is not mistaken for full crowd
simulation quality. Here, `updated` counts in-view avatars with fresh joint
data while the update is within budget; it is not a count of every simulated
avatar. `aggregate.csv` combines repeated stages with the same replica count.
