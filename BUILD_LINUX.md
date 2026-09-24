<!--
Copyright 2013-2019 High Fidelity, Inc.
Copyright 2019-2022 Vircadia contributors
Copyright 2021-2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Build Linux

Please read the [general build guide](BUILD.md) for information on dependencies required for all platforms. Only Linux specific instructions are found in this file.

~~You can use the [Overte Builder](https://github.com/overte-org/overte-builder) to build on Linux more easily. Alternatively, you can follow the manual steps below.~~ (Currently outdated.)

This documentation assumes that you are running our current target distribution, which is currently Ubuntu 22.04. The target distribution is usually the latest Ubuntu LTS still receiving standard support, though we may upgrade a little sooner if we require certain newer packages. Ubuntu version numbers are date codes and standard support is 5 years, meaning that Ubuntu 22.04 leaves standard support after around 2027-04.

## Install build tools:

-  First update the package cache and your system:
```bash
sudo apt update
sudo apt upgrade
```

-  Install Git, a C++ compiler, and Ninja
```bash
sudo apt install git g++ ninja-build
```

-  Install CMake
Use the CMake minimum in [the general build guide](BUILD.md). Ubuntu 22.04's
CMake 3.22.1 is below that minimum; Kitware provides newer packages at
https://apt.kitware.com/.

-  Install Conan
Get the Conan "Ubuntu / Debian installer" from https://conan.io/downloads and install it using:
```bash
sudo apt install ./conan-*.deb
```
Verify Conan was installed by running `conan --version`.

## Install build dependencies:
Most dependencies will be automatically installed by Conan. This section only lists dependencies which might not be handled by Conan.

- OpenGL:
```bash
sudo apt-get install libgl1-mesa-dev -y
```
Verify OpenGL:
  - First install mesa-utils with the command `sudo apt install mesa-utils -y`.
  - Then run `glxinfo | grep "OpenGL version"`.

- Qt5 source package:
```bash
sudo apt install libpulse-dev libasound2-dev python3-html5lib
```

## Extra dependencies to compile Interface on a server
- Install the following:
```bash
sudo apt install libpulse0 libnss3 libnspr4 libfontconfig1 libxcursor1 libxcomposite1 libxtst6 libxslt1.1
```

-  Misc dependencies:
```bash
sudo apt install libasound2 libxmu-dev libxi-dev freeglut3-dev libasound2-dev libjack0 libjack-dev libxrandr-dev libudev-dev libssl-dev zlib1g-dev
```

- Install a Python version that satisfies [the general build guide](BUILD.md)
  and the matching `distro` package. The distribution's default `python3` may be
  older than the repository tooling requires. Check `python3 --version` before
  running the tests; do not replace the operating system's Python in place.
```bash
sudo apt install python3 python3-distro
```

- Install Node.js using the version described in
  [the general build guide](BUILD.md); the distribution's default package may
  be older. Node.js is used by JSDoc and the repository tests.

## Get code and checkout the branch you need

Clone this repository:
```bash
git clone https://github.com/noah-be/overte.git
cd overte
```

Then check out this fork's default `main` branch:
```bash
git switch main
```

The official upstream repository uses `master`; this fork uses `main`. See the
[upstream intake policy](docs/UPSTREAM_INTAKE.md) before combining the two.

Select a product branch using the [platform guide index](docs/interfaces/README.md).
To inspect available release tags separately:
```bash
git fetch --tags
git tag
```

## Prepare conan

The next step is setting up conan

First, create a conan profile
```bash
conan profile detect --force
```

Next, add the overte remote to conan
```bash
conan remote add overte https://artifactory.overte.org/artifactory/api/conan/overte -f
```

Let conan automatically install the required system packages
```bash
echo "tools.system.package_manager:mode = install" >> ~/.conan2/global.conf
echo "tools.system.package_manager:sudo = True" >> ~/.conan2/global.conf
```
If you don't do this, Conan will still complain if it notices system packages being missing, so you can manually install them.

## Compiling

Install the dependencies with conan
```bash
conan install . -s build_type=Release -b missing -pr:a=tools/conan-profiles/linux -of build -c tools.cmake.cmaketoolchain:generator="Ninja Multi-Config"
```

If you want to build Debug or RelWithDebInfo versions, change the `build_type` to `Debug` or `RelWithDebInfo` and run the command again. E.g.:
```bash
conan install . -s build_type=Debug -b missing -pr:a=tools/conan-profiles/linux -of build -c tools.cmake.cmaketoolchain:generator="Ninja Multi-Config"
```

Prepare ninja files:
```bash
cmake --preset conan-default
```

### Server

To compile the Domain server:
```bash
cmake --build --preset conan-release --target domain-server assignment-client
```

*Note: For a server, it is not necessary to compile the Interface.*

### Interface

To compile the Interface client:
```bash
cmake --build --preset conan-release --target interface
```

## Running the software

The following paths assume the Ninja Multi-Config `Release` build above and a
shell in the repository root. Other build directories or configurations change
the corresponding path.

### Domain server

Running Domain server:
```bash
./build/domain-server/Release/domain-server
```

### Assignment clients

Running assignment client:
```bash
./build/assignment-client/Release/assignment-client -n 6
```

### Interface

Running Interface:
```bash
./build/interface/Release/interface
```

Go to "localhost" in the running Interface to visit your newly launched Domain server.

### Testing

Start with the [project testing guide](tests/PROJECT_TESTING.md) for repository
checks, portable C++/QML contracts, and the limits of host evidence.

For the native C++/Qt tests, first install the Debug dependencies as described
above, then configure the same Ninja Multi-Config build with tests enabled:

```bash
cmake --preset conan-default -DOVERTE_BUILD_TESTS=ON
OVERTE_TEST_BUILD_CONFIG=Debug bash tests/project-native-test.sh build
```

The helper builds `all-tests` and runs CTest against `build`, reporting failure
when no tests are registered. To inspect individual registered tests, use
`ctest --test-dir build -C Debug -N`; use `-R PATTERN` to run a selection.
Tests are registered in [tests/CMakeLists.txt](tests/CMakeLists.txt) and its
component directories. Follow a neighboring suite when adding a regression.
