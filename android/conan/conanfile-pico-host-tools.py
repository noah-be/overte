"""Native tools required while generating shaders for the Pico client."""

from conan import ConanFile


class PicoHostTools(ConanFile):
    name = "pico-host-tools"
    version = "1.0"
    settings = "os", "arch", "compiler", "build_type"

    def requirements(self):
        self.requires("glslang/1.4.350.0")
        self.requires("scribe/2019.02@overte/stable")
        self.requires("spirv-cross/1.4.350.0")
        self.requires("spirv-tools/1.4.350.0")
