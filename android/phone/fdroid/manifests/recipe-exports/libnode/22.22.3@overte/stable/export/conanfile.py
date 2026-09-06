import os
import shutil

from conan import ConanFile
from conan.tools.build import build_jobs
from conan.tools.env import Environment
from conan.tools.files import copy, get, replace_in_file
from conan.tools.gnu import AutotoolsToolchain, PkgConfigDeps


class LibnodeAndroidConan(ConanFile):
    name = "libnode"
    version = "22.22.3"
    user = "overte"
    channel = "stable"
    license = "MIT"
    settings = "os", "compiler", "build_type", "arch"
    package_type = "shared-library"

    def build_requirements(self):
        self.tool_requires("nasm/2.15.05")

    def requirements(self):
        self.requires(
            "openssl/3.5.8@overte/stable",
            headers=True,
            libs=True,
            transitive_libs=True,
        )
        self.requires("zlib/[>=1.3 <1.4]")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)
        # configure.py applies shared-library paths to both GYP toolsets by
        # default. Android zlib/OpenSSL belong only to target links; Linux
        # node_js2c/mksnapshot must not consume their Bionic/ARM64 objects.
        replace_in_file(
            self,
            "configure.py",
            "  if getattr(options, shared_lib):\n",
            "  if (options.cross_compiling and flavor == 'android' and\n"
            "      lib in ('openssl', 'zlib')):\n"
            "    target_output = {'include_dirs': [], 'libraries': []}\n"
            "    output.setdefault('target_conditions', []).append(\n"
            "        ['_toolset==\"target\"', target_output])\n"
            "    output = target_output\n\n"
            "  if getattr(options, shared_lib):\n",
        )
        # Node's bundled c-ares selects its Linux configuration during this
        # cross build. bionic has getservbyport(), but not the glibc-specific
        # re-entrant getservbyport_r() API advertised by that configuration.
        replace_in_file(
            self,
            "deps/cares/config/linux/ares_config.h",
            "#define HAVE_GETSERVBYPORT_R 1",
            "#if !defined(__ANDROID__)\n#define HAVE_GETSERVBYPORT_R 1\n#endif",
        )
        replace_in_file(
            self,
            "deps/cares/config/linux/ares_config.h",
            "#define HAVE_GETRANDOM 1",
            "#if !defined(__ANDROID__)\n#define HAVE_GETRANDOM 1\n#endif",
        )
        replace_in_file(
            self,
            "deps/v8/src/base/debug/stack_trace_posix.cc",
            "#if V8_LIBC_GLIBC || V8_LIBC_BSD || V8_LIBC_UCLIBC || V8_OS_SOLARIS",
            "#if !defined(__ANDROID__) && (V8_LIBC_GLIBC || V8_LIBC_BSD || "
            "V8_LIBC_UCLIBC || V8_OS_SOLARIS)",
        )
        # V8's GYP port omits Android from the POSIX trap-handler conditions.
        # This breaks both the native ARM64 target and the x64 mksnapshot host
        # tool used during an Android cross build.
        replace_in_file(
            self,
            "tools/v8_gypfiles/v8.gyp",
            'OS in "linux mac ios freebsd openharmony"',
            'OS in "linux mac ios freebsd android openharmony"',
        )
        replace_in_file(
            self,
            "tools/v8_gypfiles/v8.gyp",
            'OS in "linux mac openharmony"',
            'OS in "linux mac android openharmony"',
        )
        replace_in_file(
            self,
            "tools/v8_gypfiles/v8.gyp",
            'OS in "linux mac win openharmony"',
            'OS in "linux mac win android openharmony"',
        )
        # Android provides the POSIX realtime APIs in libc and has no librt.
        # Keeping a valid library token avoids gyp turning an empty list item
        # into the current source directory on its generated link line.
        for gyp_file in (
            "node.gypi",
            "tools/v8_gypfiles/v8.gyp",
            "deps/uv/uv.gyp",
        ):
            replace_in_file(self, gyp_file, "'-lrt'", "'-ldl'")

    def generate(self):
        AutotoolsToolchain(self).generate()
        PkgConfigDeps(self).generate()
        ndk = self.conf.get("tools.android:ndk_path")
        android_env = Environment()
        node_arch = "x64" if str(self.settings.arch) == "x86_64" else "arm64"
        android_env.define(
            "GYP_DEFINES",
            f"target_arch={node_arch} v8_target_arch={node_arch} "
            f"android_target_arch={node_arch} host_os=linux OS=android "
            f"android_ndk_path={ndk}",
        )
        # GYP's host toolset must remain executable on the build machine.
        android_env.define("CC_host", "gcc")
        android_env.define("CXX_host", "g++")
        android_env.vars(self).save_script("node_android_cross")

    def _shared_args(self, package, library):
        dependency = self.dependencies[package].cpp_info
        libs = list(dependency.libs) + list(dependency.system_libs)
        for component in dependency.components.values():
            libs += component.libs
            libs += component.system_libs
        return [
            f"--shared-{library}",
            f"--shared-{library}-includes={','.join(dependency.includedirs)}",
            f"--shared-{library}-libname={','.join(libs)}",
            f"--shared-{library}-libpath={','.join(dependency.libdirs)}",
        ]

    def build(self):
        args = [
            "--shared",
            "--without-npm",
            "--without-corepack",
            "--without-intl",
            "--v8-enable-object-print",
            "--dest-os=android",
            "--cross-compiling",
            f"--prefix={self.package_folder}",
        ]
        # Toolset ownership, not CPU-name inequality, separates the host tools.
        # Every Android target keeps the source-only external OpenSSL3.5.8 graph.
        args += self._shared_args("openssl", "openssl")
        args += self._shared_args("zlib", "zlib")
        if self.settings.build_type == "Debug":
            args.append("--debug")
        node_arch = "x64" if str(self.settings.arch) == "x86_64" else "arm64"
        args.append(f"--dest-cpu={node_arch}")

        self.run(
            f"python3 configure.py {' '.join(args)}",
            env=["conanbuild", "node_android_cross"],
        )
        self.run(
            f"make -j{build_jobs(self)} libnode -C out "
            f"BUILDTYPE={self.settings.build_type}",
            env=["conanbuild", "node_android_cross"],
        )

    def package(self):
        self.run(
            "python3 ./tools/install.py --headers-only "
            f"--dest-dir={self.package_folder}/ --prefix / install"
        )
        copy(
            self,
            "*.h",
            os.path.join(self.source_folder, "deps", "v8", "include", "libplatform"),
            os.path.join(self.package_folder, "include", "libplatform"),
            keep_path=False,
        )
        copy(
            self,
            "*.h",
            os.path.join(self.source_folder, "deps", "v8", "include", "cppgc"),
            os.path.join(self.package_folder, "include", "cppgc"),
            keep_path=False,
        )
        # GYP copies the finished target DSO to this top-level output. Recursive
        # globs also collect obj.host archives and non-relocatable thin archives
        # referencing build-only objects, none of which this shared package uses.
        library_dir = os.path.join(self.package_folder, "lib")
        os.makedirs(library_dir, exist_ok=True)
        shutil.copy2(
            os.path.join(self.source_folder, "out", str(self.settings.build_type), "libnode.so"),
            os.path.join(library_dir, "libnode.so"),
        )

    def package_info(self):
        self.cpp_info.includedirs = ["include", "include/node"]
        # libnode.so already contains Node's bundled static dependencies.
        # collect_libs() also exposes host-tool archives produced during the
        # Android cross build (for example obj.host/libabseil.a), which makes
        # downstream ARM64 links try to consume x86-64 objects.
        self.cpp_info.libs = ["node"]
