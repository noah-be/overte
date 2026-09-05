import os

from conan import ConanFile
from conan.tools.files import apply_conandata_patches, copy, export_conandata_patches, get


class GifCreatorSourceConan(ConanFile):
    name = "gifcreator"
    version = "2016.11"
    user = "overte"
    channel = "stable"
    package_type = "header-library"
    license = "Unlicense"
    homepage = "https://github.com/charlietangora/gif-h"
    description = "Canonical public-domain gif-h snapshot used as GifCreator"
    settings = "os", "arch"

    def export_sources(self):
        export_conandata_patches(self)

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)
        apply_conandata_patches(self)

    def package(self):
        copy(
            self,
            "gif.h",
            src=self.source_folder,
            dst=os.path.join(self.package_folder, "include"),
        )
        os.rename(
            os.path.join(self.package_folder, "include", "gif.h"),
            os.path.join(self.package_folder, "include", "GifCreator.h"),
        )
        copy(
            self,
            "LICENSE",
            src=self.source_folder,
            dst=os.path.join(self.package_folder, "licenses"),
        )

    def package_id(self):
        self.info.clear()

    def package_info(self):
        self.cpp_info.bindirs = []
        self.cpp_info.libdirs = []
        self.cpp_info.set_property("cmake_file_name", "GifCreator")
        self.cpp_info.set_property("cmake_target_name", "GifCreator::GifCreator")
