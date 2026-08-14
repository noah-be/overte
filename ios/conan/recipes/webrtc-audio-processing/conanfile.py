"""Static WebRTC audio-processing package for the audited iOS graph."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.env import VirtualBuildEnv
from conan.tools.files import collect_libs, get
from conan.tools.gnu import PkgConfigDeps
from conan.tools.layout import basic_layout
from conan.tools.meson import Meson, MesonToolchain


class WebRTCAudioProcessingIOSConan(ConanFile):
    name = "webrtc-audio-processing"
    version = "2.1"
    package_type = "library"
    implements = ["auto_shared_fpic"]
    license = "MIT"
    homepage = "https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing"
    description = "Audited static WebRTC audio processing build for Overte on iOS"
    settings = "os", "arch", "compiler", "build_type"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}

    def layout(self):
        basic_layout(self, src_folder="src")

    def validate(self):
        if str(self.settings.os) != "iOS" or str(self.settings.arch) != "armv8":
            raise ConanInvalidConfiguration("this recipe supports only arm64 iOS")
        if self.options.shared:
            raise ConanInvalidConfiguration(
                "the Overte iOS WebRTC audio-processing package must be static"
            )

    def requirements(self):
        self.requires("abseil/20250127.0")

    def build_requirements(self):
        self.tool_requires("meson/1.6.0")
        if not self.conf.get("tools.gnu:pkg_config", check_type=str):
            self.tool_requires("pkgconf/2.2.0")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        toolchain = MesonToolchain(self)
        # Keep this explicit even though MesonToolchain derives it from the
        # shared option: the package must never regress to Meson's shared default.
        toolchain.default_library = "static"
        toolchain.generate()
        PkgConfigDeps(self).generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        Meson(self).install()

    def package_info(self):
        self.cpp_info.libs = collect_libs(self)
        self.cpp_info.includedirs = ["include/webrtc-audio-processing-2"]
        # Public WebRTC headers include Abseil headers, and a static archive
        # also leaves those symbols for the final application link.  Express
        # the same dependency set as the upstream Meson target so CMakeDeps
        # propagates both includes and link libraries to audio-client.
        self.cpp_info.requires = [
            "abseil::absl_base",
            "abseil::absl_flags",
            "abseil::absl_strings",
            "abseil::absl_numeric",
            "abseil::absl_synchronization",
            "abseil::absl_bad_optional_access",
        ]
