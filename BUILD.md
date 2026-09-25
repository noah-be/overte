<!--
Copyright 2013-2019 High Fidelity, Inc.
Copyright 2020-2021 Vircadia contributors
Copyright 2021-2025 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# General Build Information

Start with the [developer guide](docs/README.md) to select the owning branch and
run repository checks before preparing a native build.

## OS Specific Build Guides

* [Build Windows](BUILD_WIN.md) - complete instructions for Windows.
* [Build Linux](BUILD_LINUX.md) - additional instructions for Linux.
* [Platform ports](docs/interfaces/README.md) - branch-specific Android Phone,
  Pico 4, and iOS build guides.
* [Build OSX](BUILD_OSX.md) - inherited historical guidance; macOS is not an
  active product target in the [fork roadmap](docs/ROADMAP.md).

## Dependencies
- [Git](https://git-scm.com/downloads): use a version with `git switch` support
  (2.23 or newer) for the documented development workflow.
- [CMake](https://cmake.org/download/): 3.24 or newer for the modern build;
  [CMakeLists.txt](CMakeLists.txt) defines the enforced minimum and the isolated
  legacy Android exception. Follow a platform guide's exact version when given.
- [Conan](https://conan.io/downloads): 2.x
- [Python](https://www.python.org/downloads/): 3.11 or newer for repository
  tooling; the [test environment](tests/PROJECT_TESTING.md) uses Python 3.12.
- [Node.js](https://nodejs.org/en/): use the Node.js 22 CI baseline for repository
  tests. Node.js also builds the server console, JSDoc, and script autocomplete;
  platform dependency pins remain authoritative for the embedded runtime.

## Conan Dependencies
Most of our dependencies are automatically fetched and built using Conan.
See the accompanying `conanfile.py` for a full list of direct dependencies.

### CMake

Overte uses CMake to generate build files and project files for your platform.

### Conan

Overte uses conan to download and build dependencies.
Conan can be downloaded from here: https://conan.io/downloads

See the accompanying `conanfile.py` for a full list of direct dependencies.

Building the dependencies can be lengthy and the resulting files will be stored in your home directory.
To move them to a different location, you can set the `CONAN_HOME` variable to any folder where you wish to install the dependencies.

Linux:

```bash
export CONAN_HOME=/path/to/directory
```

Windows:
```bash
set CONAN_HOME=/path/to/directory
```

Where `/path/to/directory` is the path to a directory where you wish the build files to get stored.

### Generating Build Files

#### Possible Environment Variables

```text
// The Interface will have a custom default home and startup location.
PRELOADED_STARTUP_LOCATION=Location/IP/URL
// The Interface will have a custom default script whitelist, comma separated, no spaces.
// This will also activate the whitelist on Interface's first run.
PRELOADED_SCRIPT_WHITELIST=ListOfEntries

// Code-signing environment variables must be set during runtime of CMake AND globally when the signing takes place.
HF_PFX_FILE=Path to certificate
HF_PFX_PASSPHRASE=Passphrase for certificate

// Determine if to utilize testing or stable directory services URLs
USE_STABLE_GLOBAL_SERVICES=1
BUILD_GLOBAL_SERVICES=STABLE
```

#### Possible CMake Variables

```text
// The URL to post the dump to.
OVERTE_BACKTRACE_URL
// The identifying tag of the release.
OVERTE_BACKTRACE_TOKEN

// The release version, e.g., 2021.3.2. For PR builds the PR number, e.g. 577.
// Not used for nightlies and development builds.
OVERTE_RELEASE_NUMBER
// The build commit, e.g., use a Git hash for the most recent commit in the branch - fd6973b.
OVERTE_GIT_COMMIT_SHORT

// The type of release.
OVERTE_RELEASE_TYPE=PRODUCTION|PR|NIGHTLY|DEV
```

#### Generate Files

```bash
conan install . -s build_type=Release -b missing -of build
cmake --preset conan-release
```

If CMake gives you the same error message repeatedly after the build fails, try removing `CMakeCache.txt`.

### Finding Dependencies

The following applies for dependencies we do not grab via Conan.

You can point our [CMake find modules](cmake/modules/) to the correct version of dependencies by setting one of the three following variables to the location of the correct version of the dependency.

In the examples below the variable $NAME would be replaced by the name of the dependency in uppercase, and $name would be replaced by the name of the dependency in lowercase (ex: OPENSSL_ROOT_DIR, openssl).

* $NAME_ROOT_DIR - pass this variable to Cmake with the -DNAME_ROOT_DIR= flag when running Cmake to generate build files
* $NAME_ROOT_DIR - set this variable in your ENV
* HIFI_LIB_DIR - set this variable in your ENV to your Overte lib folder, should contain a folder '$name'

## Optional Components

### Build Options

The following build options can be used when running CMake

* OVERTE_BUILD_CLIENT
* OVERTE_BUILD_SERVER
* OVERTE_BUILD_TESTS
* OVERTE_BUILD_TOOLS

### Developer Build Options

* OVERTE_RENDERING_BACKEND
* OVERTE_DISABLE_QML

### Devices

You can support external input/output devices such as Leap Motion, MIDI, and more by adding each individual SDK in the visible building path. Refer to the readme file available in each device folder in [interface/external/](interface/external) for the detailed explanation of the requirements to use the device.
