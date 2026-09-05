"""Neutral source-bootstrap graph; recipe implementations land in SH-001."""

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration


class OverteAndroidBootstrap(ConanFile):
    name = "overte-android-bootstrap"
    version = "1"
    package_type = "application"
    settings = "os", "arch", "compiler", "build_type"

    def validate(self):
        if str(self.settings.os) != "Linux" or str(self.settings.arch) != "x86_64":
            raise ConanInvalidConfiguration("bootstrap tools require the bound Linux x86_64 profile")

    def build_requirements(self):
        # SH-001 vendors source-only recipes before this graph is locked/built.
        self.tool_requires("cmake/3.31.12")
        self.tool_requires("meson/1.10.2")
        self.tool_requires("ninja/1.13.2")
        self.tool_requires("nasm/2.15.05")
        self.tool_requires("pkgconf/2.2.0")
