<!--
Copyright 2013-2019 High Fidelity, Inc.
Copyright 2019-2021 Vircadia contributors
Copyright 2021-2025 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

<p align="center"><a href="https://overte.org/"><picture><source srcset="interface/resources/images/brand-banner.svg?version=experimental-fork" alt="Overte experimental AI assisted fork" width="350" media="(prefers-color-scheme: dark)"><img src="interface/resources/images/brand-banner-black.svg?version=experimental-fork" alt="Overte experimental AI assisted fork" width="350"></picture></a></p>

> [!CAUTION]
> **AI-assisted experimental fork**
>
> This repository is an experimental fork of the [original Overte project](https://github.com/overte-org/overte). I am currently developing interfaces for the Pico 4 VR headset, Android phones, iPhones, iPads, and Mac computers. I am not a member of the Overte development team. I maintain this fork as a personal hobby project with the goal of making Overte playable by as many different people as possible.
>
> I use AI tools to assist with experiments and implementation work in this fork. Code in this repository may therefore be incomplete, poorly tested, insecure, or otherwise dangerous, including quick-and-dirty fixes and vulnerabilities that have not yet been identified. Building or running it may expose your device, data, accounts, or network to security risks. Review the code carefully and use it entirely at your own risk. Do not treat this fork as a clean, stable, or production-ready version of Overte.
>
> The Overte project has a [no-AI-contributions policy](https://github.com/overte-org/overte/blob/master/CONTRIBUTING.md), which I respect. AI tools help me work more efficiently, so I use them only for work maintained separately in this fork.

### Repository structure

The branches in this fork are organized by platform and device target:

```text
main
├── Android (android-main)
│   ├── Android phones (android-phone)
│   └── VR headsets (android-vr)
│       ├── Pico 4 (android-vr-pico)
│       └── Meta Quest (android-vr-quest)
└── Apple (apple-main)
    ├── iPhone and iPad (apple-ios)
    └── Mac computers (apple-macos)
```

The Android source tree mirrors the same ownership boundaries inside
[`android/`](android/README.md): shared infrastructure lives in `common`, Phone
code in `phone`, and headset code below `vr/pico` or `vr/quest`. The `vr/common`
directory is reserved for implementation genuinely shared by multiple Android
VR targets.

### Interfaces in development

The four ports use a shared documentation layout described in
[`docs/interfaces/`](docs/interfaces/README.md). The platform documentation is
maintained on its corresponding development branch.

> [!NOTE]
> The information below comes from the original Overte project. For the latest official information, see the [README in the original Overte repository](https://github.com/overte-org/overte#readme). This fork is an experimental personal hobby project and is not an official version of Overte.

<details>
<summary>Original Overte project information</summary>

### What is this?

Overte is a free and open source 3D social virtual worlds software.

* Desktop and VR use
* Hundreds of users simultaneously
* Collaborative in-world creation
* Full-body avatars
* FBX, glTF, and OBJ support
* JavaScript scripting engine
* 256km²/4096km³ world space in a server
* Fully self-hosted
* Apache 2.0

### Releases

[View Releases (and pre-releases) here](https://github.com/overte-org/overte/releases/)

### How to deploy a Server

- [For Windows and Linux](https://docs.overte.org/en/latest/host.html)

### Building

#### How to build the Interface

- [For Windows](https://github.com/overte-org/overte/blob/master/BUILD_WIN.md)
- [For Mac](https://github.com/overte-org/overte/blob/master/BUILD_OSX.md)
- [For Linux](https://github.com/overte-org/overte/blob/master/BUILD_LINUX.md)
- [For Linux - Overte Builder](https://github.com/overte-org/overte-builder)

#### How to build a Server

- [For Windows](https://github.com/overte-org/overte/blob/master/BUILD_WIN.md)
- [For Linux](https://github.com/overte-org/overte/blob/master/BUILD_LINUX.md)
- [For Linux - Overte Builder](https://github.com/overte-org/overte-builder)

#### How to generate an Installer

- [For Windows - Interface & Server](https://github.com/overte-org/overte/blob/master/INSTALLER.md)
- [For Mac - Interface](https://github.com/overte-org/overte/blob/master/INSTALLER.md)
- [For Linux - Interface AppImage & Server .deb/.rpm - Overte Builder](https://github.com/overte-org/overte/blob/master/INSTALLER.md)

### Mission statement

Overte aims to provide social virtual worlds experiences with entirely free and open source infrastructure.

### Technical details

Overte consists of many projects and codebases with its unifying structure's goal being free and open source self-hosted virtual worlds.

- The Interface - You are here!
- The Server - You are also here!
- [The Directory Server (Codename Iamus)](https://github.com/overte-org/overte-metaverse/)
- [The Directory Server Dashboard (Codename Iamus)](https://github.com/overte-org/metaverse-dashboard/)
- [Our downstream Conan recipies](https://github.com/overte-org/overte-conan-recipes)

#### Tools
- [Overte Builder for Linux](https://github.com/overte-org/overte-builder/)

#### Documentation
- [User Documentation](https://github.com/overte-org/overte-docs-sphinx/)
- [API Documentation (JavaScript)](https://apidocs.overte.org/) - Generated using JSDoc [here](https://github.com/overte-org/overte/tree/master/tools/jsdoc).
- [Doxygen (C++)](https://doxygen.overte.org/)

### Contribution

There are many contributors to Overte.
Code writers, reviewers, testers, documentation writers, modellers, and general supporters of the project are all integral to its development and success towards its goals.
Find out how you can [contribute](https://docs.overte.org/en/latest/contribute.html)!

</details>
