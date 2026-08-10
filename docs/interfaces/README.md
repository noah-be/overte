# Experimental Interface ports

> [!CAUTION]
> These ports are developed in an AI-assisted experimental fork. They may be
> incomplete, insufficiently tested, insecure, or unsuitable for valuable
> accounts and production use. Review the source and platform-specific status
> before building, installing, or distributing an application.

The experimental Overte Interface ports use one documentation layout so that
support boundaries, build commands, test evidence, and release readiness can be
compared without guessing which document is authoritative.

| Platform | Documentation path | Development branch |
| --- | --- | --- |
| Pico 4 | `docs/interfaces/pico4/README.md` | `android-vr-pico` |
| Android phones | `docs/interfaces/android-phone/README.md` | `android-phone` |
| iPhone and iPad | `docs/interfaces/ios/README.md` | `apple-ios` |
| macOS | `docs/interfaces/macos/README.md` | `apple-macos` |

The platform branches contain the corresponding documentation. A missing path
on another branch does not imply that the platform has been abandoned; inspect
the named development branch at its current revision.

## Shared document roles

Each platform directory should use the following files when the subject exists:

- `README.md`: maturity, support matrix, shortest safe developer path, output,
  launch instructions, important limitations, and document index.
- `BUILD.md`: host preparation, dependencies, build variants, configuration
  overrides, and output paths.
- `TESTING.md`: host tests, emulator or simulator tests, physical-device tests,
  evidence requirements, and limitations of each tier.
- `TROUBLESHOOTING.md`: symptom-based diagnosis and privacy-safe evidence
  collection.
- `SECURITY_AND_PRIVACY.md`: permissions, user data, logs, credentials, signing,
  and platform privacy requirements.
- `CI.md`: workflow names, triggers, trust boundaries, runner requirements,
  generated artifacts, and retention.
- `DEVELOPMENT_STATUS.md`: implemented behavior, verified evidence, open gates,
  and known limitations.
- `RELEASE.md`: creation and verification of installable developer artifacts.
  Store publication remains out of scope until a distribution channel is
  explicitly selected.
- `archive/`: historical work logs and superseded instructions that must not be
  followed as current guidance.

## Status vocabulary

- **Implemented** means source and build wiring exist.
- **Host-verified** means deterministic tests passed without the target runtime.
- **Simulator-verified** or **emulator-verified** means the application ran in
  that virtual target environment.
- **Device-verified** means evidence exists for the named physical device and
  source revision.
- **Build-ready** means an installable artifact can be produced and inspected;
  it does not imply device acceptance or publication readiness.
- **Experimental** means the path is available for porting work but is not an
  accepted developer or release path.

Documentation must not turn planned support into a support claim. Every runtime
claim should identify the validating environment and, when practical, the exact
source revision.

## Maintenance rules

- Keep each technical fact in one authoritative document and link to it from
  summaries instead of copying long procedures.
- A legacy entry path may remain as a short pointer, but it must not retain
  executable superseded instructions.
- Keep internal work logs under `archive/`; archived observations are evidence
  of past work, not current support claims.
- Update documented branch and workflow names together with their contract
  tests whenever repository administration changes.
