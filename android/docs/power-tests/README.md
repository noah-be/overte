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
validity has been lost. It restores the prior test-mode value as well as fan
and brightness controls on every handled exit. Run:

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

When profiling an already prepared avatar-load scene, pass
`--expect-avatar-replicas COUNT` together with `--no-prepare`. The watchdog then
requires a stable, nonzero source-avatar population and verifies once per
second that the configured number of replicas and every source and replica
skeleton model remain loaded. It rejects the profile if the crowd changes or
falls back to loading placeholders. The validated source and replica counts
are recorded in the profile metadata.

Profile metadata records whether the tracked source tree was clean and the
SHA-256 digest of the APK actually installed on the headset. This distinguishes
an experimental APK built from uncommitted changes from the named Git commit
without storing its device-specific installation path.

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
Run `./pico-graphics-matrix.sh --help` to list the available matrix modes and
environment controls; invalid modes and measurement bounds fail before ADB or
device controls are touched. Required ImageMagick commands and the visual
reference are also checked before the headset is modified.
On every handled exit, the matrix restores all graphics/debug overrides and
the prior test-mode value in addition to fan and brightness controls. It also
writes a fresh zero-duration autowalk command before stopping Interface, so an
interrupted dynamic route cannot replay on a later app start.

For a private local avatar-load smoke test, first enter an otherwise empty
domain. Create a local source from the current MyAvatar state, then create up
to 50 client-only copies of it:

```bash
cd android
./pico-unattended-test.sh avatar-template 1
./pico-unattended-test.sh replicas 5
./pico-unattended-test.sh avatar-status
./pico-unattended-test.sh replicas 0
./pico-unattended-test.sh avatar-template 0
```

The status reports total and locally replicated avatar counts, how many other
avatars and replicas have loaded skeleton models, the existing avatar
update-budget counters, and the mean avatar-simulation time across all frames
in the latest one-second status interval. It also reports how many client
updates replayed the local template packet during that interval. The loaded
counters distinguish a renderable crowd from loading-orb placeholders without
recording avatar IDs.
Replica and template commands are timestamped and ignored when stale, so an
interrupted test cannot replay its load after a later app restart. The local
template copies MyAvatar pose, identity, and skeleton traits entirely inside
the client; it sends no synthetic avatar to the domain and uses no Pico SDK or
proprietary Pico library. While the template is active, its cached complete
pose packet is replayed once per client update before other-avatar simulation.
This exercises fresh-joint-data and replica packet-decoding paths without
network transmission. Changing the count preserves each source and seeds new
replicas immediately, so an unchanged model does not remain a loading orb.
Test mode itself is re-read at runtime and disabling it removes all replicas
and the local template. Always return both the replica count and template state
to zero after a manual test.

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

The default sequence is 0, 5, 0, and 5 copies of one local template and requires
that no received other avatar be present. Repeated `--replicas` options define
a different sequence; `--received-template` retains the older mode for a
deliberately controlled received source population. The matrix fixes fan and
brightness during measurement, rejects XR-focus loss or any source-population
change, disconnect, or starting domain, and waits for every source and replica
skeleton model to load. A stage is rejected if any model returns to a loading
placeholder. The tool enables test mode for the run, writes aggregate CSV
results under `android/power-results/`, then clears the template and all copies
and restores test mode and device controls. An app restart also rejects the run
rather than mixing measurements from different processes. It never records
screenshots, avatar identifiers, or the checked domain ID. The summary includes
mean updated and budget-skipped avatar counts,
so CPU stability is not mistaken for full crowd simulation quality. Here,
`updated` counts in-view avatars with fresh joint data while the update is
within budget; it is not a count of every simulated avatar. `aggregate.csv`
combines repeated stages with the same replica count and includes mean loaded
other-avatar and loaded-replica counts plus the mean local-template refresh
count. A zero refresh count while the local template is active invalidates a
fresh-joint-data performance interpretation even if the population is stable.

Both matrix tools create an `INVALID` marker before collecting a matrix or
graphics case and remove it only after all required validation and output
steps complete. Partial diagnostic files are retained after an abort, but a
consumer can reject them without interpreting CSV or image contents.

Avatar matrices, graphics matrices, and simpleperf recordings refuse a
non-empty result directory. This prevents a retry or mistyped path from
overwriting a prior valid run or combining artifacts from different runs.

The ADB-independent control/status regressions can be run on a host without a
headset:

```bash
./tests/pico-unattended-test-test.sh
```

They cover one/zero/multiple-device selection, an explicit generic serial,
fresh and stale status, the current 20-field schema, malformed refresh data,
and replica/template command acknowledgements.

The C++ paths changed by the Pico avatar, networking, audio, and math work can
be checked without a headset as one bounded host regression run:

```bash
./tests/pico-host-regression-test.sh
```

The runner explicitly builds and executes the Animation, PositionalAudioStream,
AvatarData, Packet, ReceivedMessage, and GLMHelpers suites. It runs from the
repository root with an isolated temporary settings directory, discovers the
Qt platform plugins associated with the selected CMake build, and applies a
per-suite timeout. Use `--build-dir`, `--config`, and `--no-build` for another
configured tree whose Conan dependencies include that configuration;
`--keep-logs` retains detailed local output when diagnosing a failure. By
default, temporary logs are removed and only per-suite Qt totals are printed.
When CMake uses Conan, the runner rejects a configuration with missing Conan
package generators before starting a partial compile.
