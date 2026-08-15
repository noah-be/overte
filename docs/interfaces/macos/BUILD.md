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

For `OVERTE_RELEASE_TYPE=DEV`, the Interface `POST_BUILD` deployment keeps a
content-addressed stamp at `<build-dir>/macos-deploy/<config>/interface-bundle.json`.
After a successful clean deployment, a later relink may reuse the existing
Frameworks only when all of these are byte-identical: the Qt prefix and
`macdeployqt`, collected Conan libraries, QML input tree, deployment helpers,
the resolved non-system Mach-O dependency closure, and every application-bundle
file managed by dependency deployment. The freshly linked main executable and
application-owned `scripts`, `fonts`, `serverless`, `jsdoc`, and `resources.rcc`
payloads are independent: changing one of them does not force a clean Qt/Conan
redeployment. The incremental pass still runs `macdeployqt` to repair the new
executable and re-inspects install names, but does not clear verified Frameworks
or recopy verified Conan dylibs.

A missing/corrupt stamp, an unresolved dependency, any changed input, or a
missing/added/modified bundled file selects the original clean Frameworks
deployment. The stamp is removed before either deployment command and rewritten
atomically only after both tools succeed, so an interrupted or failed pass
cannot become a reusable checkpoint. Non-DEV packaging retains the unconditional
clean deployment path.

The build log reports `OVERTE_MACOS_BUNDLE_DEPLOY` with the selected mode,
reason, hashed input file/byte counts, resulting bundle file/byte counts, and
elapsed time. This makes the hashing cost and the avoided clean deployment
directly measurable on the macOS runner without recording source paths in the
stamp. The optimization affects only dependency deployment after an Interface
relink; compilation, linking, signing, installation, and release packaging are
outside its scope.

Runtime payloads are explicit Ninja link dependencies. Editing, adding, or
removing a script, font, or serverless fixture therefore relinks the Interface
and reruns bundle staging even when no C++ source changed. Application-owned
runtime directories are removed before they are copied, so an incremental
checkpoint cannot retain a deleted payload. JSDoc is removed unconditionally
before its optional copy, including when a tree is reconfigured from enabled to
disabled documentation.

Before dependency inspection, the Conan deployment helper checks the canonical
four-byte Mach-O/FAT magic values, including both byte orders and FAT64. Bundle
resources therefore do not spawn `otool`; only actual Mach-O candidates are
inspected. The observed bundle inventory was about 3,393 files versus about 248
Mach-O files, so this prefilter removes roughly 93% of those process launches
without changing which binaries are rewritten.

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
