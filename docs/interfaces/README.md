# Experimental Interface ports

> [!CAUTION]
> These ports are developed in an AI-assisted experimental fork. They may be
> incomplete, insufficiently tested, insecure, or unsuitable for valuable
> accounts and production use. Review the source and platform-specific status
> before building, installing, or distributing an application.

The experimental Overte Interface ports use one documentation layout so that
support boundaries, build commands, test evidence, and release readiness can be
compared without guessing which document is authoritative.

| Platform | Developer entry point | Build instructions |
| --- | --- | --- |
| Android phones | [`android-phone` guide](https://github.com/noah-be/overte/blob/android-phone/docs/interfaces/android-phone/README.md) | [Phone build](https://github.com/noah-be/overte/blob/android-phone/docs/interfaces/android-phone/BUILD.md) |
| Pico 4 | [`android-vr-pico` guide](https://github.com/noah-be/overte/blob/android-vr-pico/docs/interfaces/pico4/README.md) | [Pico build](https://github.com/noah-be/overte/blob/android-vr-pico/docs/interfaces/pico4/BUILD.md) |
| iPhone and iPad | [`apple-ios` guide](https://github.com/noah-be/overte/blob/apple-ios/docs/interfaces/ios/README.md) | [iOS build](https://github.com/noah-be/overte/blob/apple-ios/docs/interfaces/ios/BUILD.md) |

The active platform branches contain their corresponding documentation.
Historical platform documentation may remain on a frozen archival branch, but
it is not a current development or support target.

Read the target's current status before running its build commands. Its build
host and dependencies may differ from the shared repository checks. For shared
changes, use the [source ownership guide](../SOURCE_LAYOUT.md); for Linux and
Windows, use the [general build guide](../../BUILD.md).

## Shared document roles

Each platform directory should use the following files when the subject exists:

- `README.md`: maturity, support matrix, shortest safe developer path, output,
  launch instructions, important limitations, and document index.
- `ROADMAP.md`: current milestone, no more than seven exit criteria, exactly one
  next action, blockers, and explicit non-goals. Start from
  [`ROADMAP_TEMPLATE.md`](ROADMAP_TEMPLATE.md).
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

- Keep repository priority and product order in [`../ROADMAP.md`](../ROADMAP.md);
  keep detailed product milestones on the corresponding product branch.
- Keep each technical fact in one authoritative document and link to it from
  summaries instead of copying long procedures.
- Keep priority and maturity separate: priority says what is being worked on,
  while maturity says what has been verified.
- Keep exactly one single next action in every active product roadmap.
- A legacy entry path may remain as a short pointer, but it must not retain
  executable superseded instructions.
- Keep internal work logs under `archive/`; archived observations are evidence
  of past work, not current support claims.
- Update documented branch and workflow names together with their contract
  tests whenever repository administration changes.
