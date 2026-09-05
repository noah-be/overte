import os
import shlex

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.build import build_jobs
from conan.tools.files import copy, get
from conan.tools.layout import basic_layout


class CMakeSourceConan(ConanFile):
    name = "cmake"
    package_type = "application"
    license = "BSD-3-Clause"
    homepage = "https://cmake.org"
    description = "Source-built CMake for the Overte F-Droid bootstrap graph"
    settings = "os", "arch", "compiler", "build_type"

    def layout(self):
        basic_layout(self, src_folder="src")

    def validate(self):
        if str(self.settings.os) != "Linux" or str(self.settings.arch) != "x86_64":
            raise ConanInvalidConfiguration(
                "the source bootstrap is bound to Linux x86_64"
            )

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def build(self):
        bootstrap = shlex.quote(os.path.join(self.source_folder, "bootstrap"))
        prefix = shlex.quote(self.package_folder)
        self.run(
            f"{bootstrap} --prefix={prefix} --parallel={build_jobs(self)} "
            "--no-qt-gui --no-system-libs -- -DCMAKE_USE_OPENSSL=OFF"
        )
        self.run(f"make -j{build_jobs(self)}")

    def package(self):
        self.run("make install")
        copy(
            self,
            "Copyright.txt",
            src=self.source_folder,
            dst=os.path.join(self.package_folder, "licenses"),
        )

    def package_info(self):
        self.cpp_info.includedirs = []
        self.cpp_info.libdirs = []
        self.buildenv_info.prepend_path("PATH", os.path.join(self.package_folder, "bin"))
