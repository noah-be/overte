# Overte for macOS

> [!CAUTION]
> This is an AI-assisted experimental port. It is incomplete, has not completed
> release acceptance, and is not a production-ready Overte release. Review the
> source and current status before using valuable accounts or distributing the
> application.

## Current status

The goal is an Overte desktop application that can load local serverless scenes
and online domains on macOS. The current bootstrap path uses Qt 5 and OpenGL 4.1
and targets Intel (`x86_64`) first. The Intel developer bundle now builds,
launches, loads the deterministic local scene, connects to the public Overte
Hub, receives entities, renders them, captures non-empty images, and exits
cleanly. Comprehensive GitHub Actions run
[`31821239596`](https://github.com/noah-be/overte/actions/runs/31821239596)
built and bundled the app, passed startup, serverless, online, graphics and
performance acceptance, and completed all 50 native C++/Qt tests without a
failure or skip. Earlier run
[`31778713708`](https://github.com/noah-be/overte/actions/runs/31778713708)
also passed a same-process serverless-online-serverless transition.

Apple Silicon (`arm64`) is an intended target and the build script accepts it,
but its Qt and native dependency graph has not been validated. Do not interpret
configuration support as a working native Apple Silicon build.

Product development is currently paused because no physical Mac test hardware
is available and further virtual/software-renderer testing is too costly to
replace the required hardware evidence. See the roadmap before starting new
macOS work.

## Support matrix

| Area | Current configuration |
| --- | --- |
| Build host | macOS with Xcode command-line tools |
| Target OS | macOS 11.0 or newer build target; CI runtime validated on macOS 15 Intel |
| Architecture | `x86_64` bootstrap; `arm64` preparation only |
| Graphics | OpenGL 4.1; CI evidence uses Apple's virtualized software renderer |
| Virtual target | GitHub `macos-15-intel` runtime acceptance |
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

- Native Apple Silicon dependencies are not validated.
- The public online smoke depends on an external Overte place and network.
- Apple's virtualized software OpenGL renderer compiles some complex pipelines
  pathologically slowly; deterministic tests suppress the local avatar and
  unrelated system scripts, but normal application use does not.
- Signing, notarization, installer creation, and public distribution are out of
  scope for the current milestone.
- Apple's OpenGL implementation is deprecated and limited to 4.1. MoltenVK is a
  possible later rendering path, not a current fallback.

## Documentation

- [Roadmap and paused hardware gate](ROADMAP.md)
- [Complete build guide](BUILD.md)
- [Testing](TESTING.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Continuous integration](CI.md)
- [Development status](DEVELOPMENT_STATUS.md)
- [Developer artifacts](RELEASE.md)
