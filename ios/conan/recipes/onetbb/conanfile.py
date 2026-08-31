"""Static oneTBB package used only by the audited iOS dependency graph."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import os

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout
from conan.tools.files import copy, get, rmdir


class OneTBBIOSConan(ConanFile):
    name = "onetbb"
    version = "2021.10.0"
    package_type = "library"
    implements = ["auto_shared_fpic"]
    license = "Apache-2.0"
    homepage = "https://github.com/oneapi-src/oneTBB"
    description = "Audited static oneTBB build for Overte on iOS"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "tbbmalloc": [True, False],
        "tbbproxy": [True, False],
        "interprocedural_optimization": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "tbbmalloc": False,
        "tbbproxy": False,
        "interprocedural_optimization": False,
    }

    def configure(self):
        if not self.options.tbbmalloc:
            self.options.rm_safe("tbbproxy")

    def layout(self):
        cmake_layout(self, src_folder="src")

    def validate(self):
        if str(self.settings.os) != "iOS" or str(self.settings.arch) != "armv8":
            raise ConanInvalidConfiguration("this recipe supports only arm64 iOS")
        if self.options.shared:
            raise ConanInvalidConfiguration("the Overte iOS oneTBB package must be static")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        toolchain = CMakeToolchain(self)
        toolchain.cache_variables["BUILD_SHARED_LIBS"] = False
        toolchain.cache_variables["TBB_TEST"] = False
        toolchain.cache_variables["TBB_STRICT"] = False
        toolchain.cache_variables["TBBMALLOC_BUILD"] = bool(self.options.tbbmalloc)
        toolchain.cache_variables["TBBMALLOC_PROXY_BUILD"] = bool(
            self.options.get_safe("tbbproxy", False)
        )
        toolchain.cache_variables["TBB_ENABLE_IPO"] = bool(
            self.options.interprocedural_optimization
        )
        toolchain.cache_variables["TBB_DISABLE_HWLOC_AUTOMATIC_SEARCH"] = True
        toolchain.cache_variables["CMAKE_POLICY_VERSION_MINIMUM"] = "3.5"
        toolchain.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(
            self,
            "LICENSE.txt",
            src=self.source_folder,
            dst=os.path.join(self.package_folder, "licenses"),
        )
        rmdir(self, os.path.join(self.package_folder, "lib", "cmake"))
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        rmdir(self, os.path.join(self.package_folder, "share"))

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "TBB")
        component = self.cpp_info.components["libtbb"]
        component.set_property("cmake_target_name", "TBB::tbb")
        component.libs = ["tbb_debug" if self.settings.build_type == "Debug" else "tbb"]
