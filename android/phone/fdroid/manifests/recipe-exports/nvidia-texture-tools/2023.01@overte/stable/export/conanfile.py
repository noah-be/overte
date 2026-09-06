from conan import ConanFile
from conan.tools.files import collect_libs, get, replace_in_file
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout


class NvidiaTextureToolsConan(ConanFile):
    name = "nvidia-texture-tools"
    version = "2023.01"
    user = "overte"
    channel = "stable"
    license = "MIT"
    settings = "os", "compiler", "build_type", "arch"

    def layout(self):
        cmake_layout(self)

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)
        # Android's bionic libc intentionally does not expose the glibc
        # unlocked stdio and execinfo APIs used by this old Linux path.
        # The preprocessor guards keep behavior unchanged on desktop Linux.
        replace_in_file(
            self,
            "src/nvcore/StdStream.h",
            "#elif NV_OS_LINUX",
            "#elif NV_OS_LINUX && !defined(__ANDROID__)",
            encoding="latin-1",
        )
        replace_in_file(
            self,
            "src/nvcore/Debug.cpp",
            "defined(HAVE_EXECINFO_H)",
            "(defined(HAVE_EXECINFO_H) && !defined(__ANDROID__))",
            encoding="latin-1",
        )

    def generate(self):
        toolchain = CMakeToolchain(self)
        toolchain.variables["BUILD_TESTS"] = "OFF"
        toolchain.variables["BUILD_TOOLS"] = "OFF"
        toolchain.variables["USE_CUDA"] = "OFF"
        toolchain.cache_variables["CMAKE_POLICY_VERSION_MINIMUM"] = "3.5"
        toolchain.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.cpp_info.libs = collect_libs(self)
