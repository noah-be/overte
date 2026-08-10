# Overte for macOS

> [!CAUTION]
> This is an AI-assisted experimental port. It is incomplete, has not completed
> runtime acceptance, and is not a production-ready Overte release. Review the
> source and current status before using valuable accounts or distributing the
> application.

## Current status

The goal is an Overte desktop application that can load local serverless scenes
and online domains on macOS. The current bootstrap path uses Qt 5 and OpenGL 4.1
and targets Intel (`x86_64`) first. Dependency resolution is still being repaired
and no current revision has completed the build and runtime gates.

Apple Silicon (`arm64`) is an intended target and the build script accepts it,
but its Qt and native dependency graph has not been validated. Do not interpret
configuration support as a working native Apple Silicon build.

## Support matrix

| Area | Current configuration |
| --- | --- |
| Build host | macOS with Xcode command-line tools |
| Target OS | macOS 11.0 or newer build target; runtime support not yet validated |
| Architecture | `x86_64` bootstrap; `arm64` preparation only |
| Graphics | OpenGL 4.1 bootstrap |
| Virtual target | No VM workflow is defined or required |
| Physical target | A Mac is required for build and runtime validation |

## Quick start

Install Xcode and make `cmake`, Conan 2, Python 3, Node.js, and `aqtinstall`
available. Then run from the repository root:

```bash
macos/build-macos.sh doctor
macos/build-macos.sh all
```

The first command is read-only. The second resolves the dependency graph,
configures a client-only build, and attempts to build `Overte.app`.

## Output and launch

The expected developer artifact is `build/interface/Overte.app`. Once the build
gate succeeds, launch it locally with:

```bash
open build/interface/Overte.app
```

The current workflow does not establish a distribution signature, notarization,
or a generally distributable application. Developer-local installation and
testing are the only release goal at this stage.

## Known limitations

- The latest recorded CI attempt stopped during the Node dependency build.
- Runtime launch, first frame, serverless loading, and online-domain loading
  still require successful evidence on a Mac.
- Native Apple Silicon dependencies are not validated.
- Signing, notarization, installer creation, and public distribution are out of
  scope for the current milestone.
- Apple's OpenGL implementation is deprecated and limited to 4.1. MoltenVK is a
  possible later rendering path, not a current fallback.

## Documentation

- [Complete build guide](BUILD.md)
- [Testing](TESTING.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Continuous integration](CI.md)
- [Development status](DEVELOPMENT_STATUS.md)
- [Developer artifacts](RELEASE.md)
