"""Linux x86_64 Qt and shader tools used by the Android source graph."""

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration


QT_REF = (
    "qt/5.15.18-2026.01.04@overte/stable"
    "#c615fd9bf2e6410b92a3e6b84fa73980"
)


class OverteAndroidHostTools(ConanFile):
    name = "overte-android-host-tools"
    version = "1"
    package_type = "application"
    settings = "os", "arch", "compiler", "build_type"

    def validate(self):
        if str(self.settings.os) != "Linux" or str(self.settings.arch) != "x86_64":
            raise ConanInvalidConfiguration(
                "Android host tools require the bound Linux x86_64 profile"
            )

    def requirements(self):
        self.requires(QT_REF, run=True)
        self.requires("glslang/1.4.350.0", run=True)
        self.requires("scribe/2019.02@overte/stable", run=True)
        self.requires("spirv-cross/1.4.350.0", run=True)
        self.requires("spirv-tools/1.4.350.0", run=True)
