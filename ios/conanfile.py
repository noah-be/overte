"""Staged Conan graph for validating native iOS dependencies.

The main Overte recipe still describes the desktop graph. This recipe keeps the
first iOS dependency audit small and explicit so desktop-only packages cannot
enter the application by accident.
"""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.cmake import CMakeDeps, CMakeToolchain


class OverteIOSDependencies(ConanFile):
    name = "overte-ios-dependencies"
    version = "0.1"
    package_type = "application"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "with_graphics_toolchain": [True, False],
        "with_audio": [True, False],
    }
    default_options = {
        "with_graphics_toolchain": False,
        "with_audio": True,
        "*:shared": False,
        "*:fPIC": True,
        "openssl*:shared": False,
    }

    def validate(self):
        if str(self.settings.os) != "iOS":
            raise ConanInvalidConfiguration("The staged graph only supports iOS")
        if str(self.settings.arch) != "armv8":
            raise ConanInvalidConfiguration("The first iOS port only supports arm64")

    def requirements(self):
        # Baseline libraries used by networking, entities, physics and assets.
        self.requires("artery-font-format/1.0.1")
        self.requires("bullet3/3.25")
        self.requires("cgltf/1.14@overte/stable")
        self.requires("draco/1.3.5")
        self.requires("glm/0.9.9.5", force=True)
        self.requires("gli/cci.20210515")
        self.requires("jsoncpp/1.9.6", force=True)
        self.requires("nlohmann_json/3.11.2")
        self.requires("onetbb/2021.10.0")
        self.requires("openexr/3.1.9")
        self.requires("openssl/3.5.7", force=True)
        self.requires("v-hacd/4.1.0")
        self.requires("zlib/1.3.1")

        # QuaZIP 1.4 hard-depends on Qt 5 and must never enter this graph.
        # The Qt 6 iOS integration owns a QuaZIP 1.7+ build against the same
        # audited Qt target package selected by OVERTE_IOS_QT_ROOT.

        if self.options.with_audio:
            self.requires("opus/1.5.2")
            self.requires("webrtc-audio-processing/2.1@overte/stable")

        if self.options.with_graphics_toolchain:
            self.requires("vulkan-memory-allocator/3.0.1")

    def build_requirements(self):
        if self.options.with_graphics_toolchain:
            # These executables run on the macOS build host; target-architecture
            # copies must never be selected as shader generators.
            self.tool_requires("glslang/1.4.350.0")
            self.tool_requires("scribe/2019.02@overte/stable")
            self.tool_requires("spirv-cross/1.4.350.0")
            self.tool_requires("spirv-tools/1.4.350.0")

    def generate(self):
        toolchain = CMakeToolchain(self)
        toolchain.cache_variables["CMAKE_OSX_DEPLOYMENT_TARGET"] = "17.0"
        toolchain.cache_variables["CMAKE_OSX_ARCHITECTURES"] = "arm64"
        toolchain.generate()
        CMakeDeps(self).generate()
