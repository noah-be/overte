# Overte for iPhone and iPad

The authoritative platform entry point is
[`docs/interfaces/ios/README.md`](../docs/interfaces/ios/README.md).

Use `./ios/build-ios.sh --help` from the repository root to inspect the build
commands. The validated bootstrap and the experimental integrated Overte client
are different targets; read the platform status before building or installing
either one.

## Compiler budget

The shared Apple build CLI defaults to two compiler jobs. Set
`OVERTE_IOS_BUILD_JOBS` to a positive integer to select another local budget;
invalid values fail before invoking build tools. The CLI passes the budget to
CMake and to Conan package compilation in both build and host contexts.

The integrated and Qt provisioning workflows use two jobs. Their common CI
environment is initialized with
`python3 ios/tools/ci-build-budget.py --jobs 2 --github-env "$GITHUB_ENV"`.
This exports the CLI and CMake budgets and the pinned Autoninja's local core
addition and remote core limit. Local Autoninja adds the exported value to its
detected CPU count, yielding exactly two jobs. A CPU multiplier alone would
only affect its remote mode. This resource control preserves cache validation,
compiler inputs, signing policy and all required qualification checks.
