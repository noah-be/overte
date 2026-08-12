"""Build libnode on macOS from Node's complete official release archive."""

import os
import shlex
import shutil

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.build import check_min_cppstd
from conan.tools.env import Environment
from conan.tools.files import collect_libs, copy, get
from conan.tools.gnu import Autotools, AutotoolsToolchain, PkgConfigDeps


class OverteMacOSLibnode(ConanFile):
    name = "libnode"
    version = "22.22.3"
    license = "MIT"
    homepage = "https://nodejs.org"
    description = "Node.js shared library for Overte on macOS"
    settings = "os", "compiler", "build_type", "arch"
    package_type = "shared-library"

    def validate(self):
        if str(self.settings.os) != "Macos":
            raise ConanInvalidConfiguration("the local libnode repair recipe is macOS-only")
        if str(self.settings.arch) not in ("x86_64", "armv8"):
            raise ConanInvalidConfiguration("unsupported macOS libnode architecture")
        if self.settings.compiler.get_safe("cppstd"):
            check_min_cppstd(self, 20)

    def build_requirements(self):
        self.tool_requires("nasm/2.15.05")

    def requirements(self):
        self.requires("openssl/1.1.1w", visible=False, options={"shared": False})
        self.requires("zlib/[>=1.3 <1.4]", visible=False, options={"shared": False})

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    @staticmethod
    def _shared_args(dependency, name):
        libraries = list(dependency.cpp_info.libs) + list(dependency.cpp_info.system_libs)
        for component in dependency.cpp_info.components.values():
            libraries += component.libs
            libraries += component.system_libs
        return [
            f"--shared-{name}",
            f"--shared-{name}-includes={','.join(dependency.cpp_info.includedirs)}",
            f"--shared-{name}-libname={','.join(libraries)}",
            f"--shared-{name}-libpath={','.join(dependency.cpp_info.libdirs)}",
        ]

    def generate(self):
        AutotoolsToolchain(self).generate()
        PkgConfigDeps(self).generate()
        environment = Environment()
        environment.define("PKG_CONFIG_PATH", self.build_folder)
        environment.vars(self).save_script("node_build_env")

    def build(self):
        cpu = "arm64" if str(self.settings.arch) == "armv8" else "x64"
        node_build_type = "Debug" if str(self.settings.build_type) == "Debug" else "Release"
        args = [
            "--shared", "--without-npm", "--without-corepack", "--without-intl",
            "--v8-enable-object-print", f"--prefix={self.package_folder}",
            f"--dest-cpu={cpu}",
        ]
        args += self._shared_args(self.dependencies["openssl"], "openssl")
        args += self._shared_args(self.dependencies["zlib"], "zlib")
        if str(self.settings.build_type) == "Debug":
            args.append("--debug")
        build_environment = Environment()
        watchdog = os.environ.get("OVERTE_COMPILER_WATCHDOG", "")
        if watchdog:
            if not os.path.isfile(watchdog) or not os.access(watchdog, os.X_OK):
                raise ConanInvalidConfiguration("compiler watchdog is not executable")
            c_compiler = shutil.which("clang")
            cxx_compiler = shutil.which("clang++")
            if not c_compiler or not cxx_compiler:
                raise ConanInvalidConfiguration("Apple Clang is unavailable")
            # Node's GYP Makefiles do not understand CMake compiler launchers.
            # Put the same per-invocation watchdog in CC/CXX so every V8 object
            # is persisted through sccache immediately and remains observable.
            build_environment.define(
                "CC", shlex.join([watchdog, "--", c_compiler])
            )
            build_environment.define(
                "CXX", shlex.join([watchdog, "--", cxx_compiler])
            )
        with build_environment.vars(self).apply():
            self.run(f"python3 configure.py {' '.join(args)}", env=["node_build_env"])
            Autotools(self).make(
                # Node only generates internal include sets for Debug and Release.
                # RelWithDebInfo would silently compile without those include paths.
                args=["-C", "out", f"BUILDTYPE={node_build_type}"],
                target="libnode",
            )

    def package(self):
        self.run(
            f"python3 ./tools/install.py --headers-only "
            f"--dest-dir={self.package_folder}/ --prefix=/ install"
        )
        for include_dir in ("libplatform", "cppgc"):
            copy(
                self, "*.h",
                src=os.path.join(self.source_folder, "deps", "v8", "include", include_dir),
                dst=os.path.join(self.package_folder, "include", include_dir),
                keep_path=False,
            )
        node_build_type = "Debug" if str(self.settings.build_type) == "Debug" else "Release"
        output = os.path.join(self.source_folder, "out", node_build_type)
        copy(self, "libnode.*", src=output, dst=os.path.join(self.package_folder, "lib"), keep_path=False)
        copy(self, "*.a", src=output, dst=os.path.join(self.package_folder, "lib"), keep_path=False)

    def package_info(self):
        self.cpp_info.includedirs = ["include", "include/node"]
        self.cpp_info.libs = collect_libs(self)
