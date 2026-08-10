# Pico 4 continuous integration

The active development branch is `android-vr-pico`; the retired
`feature/pico4-support` branch must not be used.

- `Pico 4 device-free CI` runs dependency-light host checks.
- `Pico 4 trusted build` is manual and accepts only `android-vr-pico` or an
  immutable preview tag on the isolated Android build runner.
- `Pico 4 release candidate` creates signed, verified draft-candidate files from
  an immutable RC tag in a protected environment.
- `Pico 4 device acceptance` performs a separately approved, digest-bound
  installation and minimal launch test on a dedicated headset runner.

Workflow filenames, runner labels, artifacts, retention, and repository settings
are detailed in
[`android/docs/pico4-ci-cd.md`](../../../android/docs/pico4-ci-cd.md).
