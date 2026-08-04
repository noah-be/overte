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
stack data produced by Android simpleperf's 4000 Hz DWARF default. Run:

```bash
cd android
./pico-simpleperf.sh
```

Use `--call-graph fp` only when a call graph is required and the current build
has usable frame pointers. Results are written below the Git-ignored
`android/power-results/` directory. `--binary-cache` additionally resolves the
record against unstripped native build outputs, but is opt-in because a full
cache can require several gigabytes.
