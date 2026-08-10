"""Correct macOS packaging for Overte's legacy Qt 5 aqt dependency."""

import os

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.files import copy, download


class OverteMacOSAqt(ConanFile):
    name = "qt"
    version = "5.15.2"
    settings = "os", "arch"
    options = {"modules": ["ANY"]}
    default_options = {"modules": "qtwebengine"}
    package_type = "shared-library"

    def validate(self):
        if str(self.settings.os) != "Macos":
            raise ConanInvalidConfiguration("the local aqt repair recipe is macOS-only")
        if str(self.settings.arch) != "x86_64":
            raise ConanInvalidConfiguration("Qt 5.15.2 aqt is available only for macOS x86_64")

    def source(self):
        tool = os.path.join(self.source_folder, "aqt")
        download(
            self,
            "https://github.com/AnotherFoxGuy/aqtinstall-onefile/releases/latest/download/aqt-macos",
            tool,
        )
        os.chmod(tool, 0o755)

    def package(self):
        tool = os.path.join(self.source_folder, "aqt")
        self.run(
            f'"{tool}" install-qt macos desktop {self.version} clang_64 '
            f'-O "{self.build_folder}" -m {self.options.modules}'
        )
        copy(
            self,
            "*",
            src=os.path.join(self.build_folder, str(self.version), "clang_64"),
            dst=self.package_folder,
        )

    def package_info(self):
        self.buildenv_info.define_path("Qt5_ROOT", self.package_folder)
        self.runenv_info.define_path("Qt5_ROOT", self.package_folder)
