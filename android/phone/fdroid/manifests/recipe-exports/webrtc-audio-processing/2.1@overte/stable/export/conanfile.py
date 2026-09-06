import os
from conan import ConanFile
from conan.tools.layout import basic_layout
from conan.tools.files import get, collect_libs
from conan.tools.env import VirtualBuildEnv
from conan.tools.gnu import PkgConfigDeps
from conan.tools.meson import Meson, MesonToolchain
from conan.tools.scm import Version

class WAPConan(ConanFile):
    name = "webrtc-audio-processing"
    license = "MIT"
    url = "https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing"
    description = "Packaging friendly copy of the AudioProcessing module from the WebRTC project"
    settings = "os", "compiler", "build_type", "arch"

    def layout(self):
        basic_layout(self, src_folder="src")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        env = VirtualBuildEnv(self)
        env.generate()
        tc = MesonToolchain(self)
        if self.settings.os == "Windows":
            tc.project_options["cpp_std"] = "c++20" # Build fails otherwise on windows
        tc.generate()
        deps = PkgConfigDeps(self)
        deps.generate()

    def requirements(self):
        self.requires("abseil/20250127.0")

    def build_requirements(self):
        self.tool_requires("meson/1.6.0")
        if not self.conf.get("tools.gnu:pkg_config", check_type=str):
            self.tool_requires("pkgconf/2.2.0")

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        meson = Meson(self)
        meson.install()

    def package_info(self):
        self.cpp_info.libs = collect_libs(self)
        if Version(self.version).in_range(">=2.0 <3"):
            self.cpp_info.includedirs = ['include/webrtc-audio-processing-2']
