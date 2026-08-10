# Test Overte for macOS

The macOS port has no VM-based acceptance path. Build and runtime evidence must
come from a Mac.

## Static and source contracts

```bash
python3 macos/tests/source-contract-test.py
bash -n macos/build-macos.sh macos/ci/*.sh
```

These checks do not prove that the application links, launches, or renders.

## Runtime smoke tests

After `Overte.app` builds, CI and local developers can run:

```bash
macos/ci/serverless-smoke.sh build/interface/Overte.app build/macos-smoke
macos/ci/online-smoke.sh build/interface/Overte.app build/macos-online-smoke
```

The serverless gate requires a populated entity tree and render handoff from the
packaged tutorial scene. The online gate additionally requires directory and
entity-server progress. A passing process exit without the expected markers is
not acceptance.

## Physical Mac matrix

Record the exact source revision, macOS version, Xcode version, architecture,
application hash, and result. Validate Intel first. Treat Apple Silicon as a
separate target and do not substitute a Rosetta result for a native `arm64`
build.
