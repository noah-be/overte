# Build Overte for macOS

Run all commands from the repository root on macOS. The supported entry point is
`macos/build-macos.sh`; the removed legacy SDK 10.12 instructions must not be
used with a current Xcode installation.

## Requirements

- Xcode and its command-line tools
- CMake
- Conan 2
- Python 3
- Node.js
- `aqtinstall` in a Python virtual environment when using the default Qt source

Check the host without resolving or building dependencies:

```bash
macos/build-macos.sh doctor
```

## Build stages

```bash
macos/build-macos.sh deps
macos/build-macos.sh configure
macos/build-macos.sh build
```

`build` configures before compiling. Use `all` to run dependency resolution and
the build in one invocation.

The build is client-only: server, tools, tests, and installer targets are
disabled. Defaults are `RelWithDebInfo`, `x86_64`, the repaired Conan `aqt` Qt
package, and deployment target 11.0.

## Overrides

| Variable | Purpose |
| --- | --- |
| `OVERTE_MACOS_BUILD_TYPE` | Conan and CMake build type |
| `OVERTE_MACOS_ARCH` | `x86_64` or experimental `arm64` |
| `OVERTE_MACOS_QT_SOURCE` | Qt package source |
| `OVERTE_MACOS_BUILD_DIR` | Build directory |
| `OVERTE_MACOS_BUILD_TESTS` | `ON` enables registered C++/Qt test targets; default `OFF` |
| `MACOSX_DEPLOYMENT_TARGET` | macOS deployment target |

The script configures the Overte Conan remotes and exports macOS-local repairs
for the Qt and Node recipes. Those repairs are part of the experimental port and
must be validated before they are treated as reusable release dependencies.

For an explicit code-test build, configure the same client tree with tests and
then execute the common native runner:

```bash
OVERTE_MACOS_BUILD_TESTS=ON macos/build-macos.sh build
OVERTE_TEST_BUILD_CONFIG=RelWithDebInfo \
OVERTE_TEST_TIMEOUT=900 \
OVERTE_TEST_JUNIT=build/macos-native-test-results/TEST-overte-macos-native.xml \
  tests/project-native-test.sh build
```

This is intentionally opt-in because compiling every registered test executable
is substantially more expensive than the application target.
