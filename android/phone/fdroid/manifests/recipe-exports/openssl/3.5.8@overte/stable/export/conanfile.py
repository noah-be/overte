import os
import shlex

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.build import build_jobs
from conan.tools.files import copy, get, rmdir, save
from conan.tools.gnu import AutotoolsToolchain
from conan.tools.layout import basic_layout


class OpenSSLAndroidConan(ConanFile):
    name = "openssl"
    version = "3.5.8"
    user = "overte"
    channel = "stable"
    license = "Apache-2.0"
    homepage = "https://www.openssl.org"
    description = "Source-only OpenSSL provider for the bound Overte Android graph"
    settings = "os", "arch", "compiler", "build_type"
    package_type = "shared-library"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": True, "fPIC": True}

    def layout(self):
        basic_layout(self, src_folder="src")

    def validate(self):
        expected = {
            "os": "Android",
            "arch": "armv8",
            "compiler": "clang",
            "compiler.version": "18",
            "os.api_level": "26",
        }
        actual = {
            "os": str(self.settings.os),
            "arch": str(self.settings.arch),
            "compiler": str(self.settings.compiler),
            "compiler.version": str(self.settings.compiler.version),
            "os.api_level": str(self.settings.os.api_level),
        }
        mismatches = [
            f"{key}={actual[key]} (expected {value})"
            for key, value in expected.items()
            if actual[key] != value
        ]
        if mismatches:
            raise ConanInvalidConfiguration(
                "OpenSSL recipe accepts only the bound Android profile: "
                + ", ".join(mismatches)
            )
        if not self.options.shared:
            raise ConanInvalidConfiguration("OpenSSL must be shared in the Android APK graph")
        self._required_tool("user.overte:perl_path")
        self._required_tool("user.overte:make_path")
        self._android_ndk()

    def _android_ndk(self):
        ndk = self.conf.get("tools.android:ndk_path", check_type=str)
        if not ndk or not os.path.isabs(ndk):
            raise ConanInvalidConfiguration("tools.android:ndk_path must be an absolute NDK directory")
        if (str(self.settings_build.os), str(self.settings_build.arch)) != ("Linux", "x86_64"):
            raise ConanInvalidConfiguration("OpenSSL requires the bound Linux x86_64 build toolchain")
        if not os.path.isfile(os.path.join(ndk, "source.properties")):
            raise ConanInvalidConfiguration("tools.android:ndk_path must contain NDK source.properties")
        binaries = os.path.join(ndk, "toolchains", "llvm", "prebuilt", "linux-x86_64", "bin")
        for name in ("clang", "llvm-ar", "aarch64-linux-android26-clang"):
            path = os.path.join(binaries, name)
            if not os.path.isfile(path) or not os.access(path, os.X_OK):
                raise ConanInvalidConfiguration("Configured NDK lacks required executable " + name)
        return ndk, binaries

    def _required_tool(self, key):
        path = self.conf.get(key, check_type=str)
        if not path or not os.path.isabs(path) or not os.path.isfile(path):
            raise ConanInvalidConfiguration(f"{key} must name an existing absolute file")
        if not os.access(path, os.X_OK):
            raise ConanInvalidConfiguration(f"{key} must be executable")
        return path

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        ndk, binaries = self._android_ndk()
        toolchain = AutotoolsToolchain(self)
        environment = toolchain.environment()
        # OpenSSL's own Android Configure logic needs both variables even when
        # Autotools already supplies an absolute CC. Never inherit another NDK.
        environment.define("ANDROID_NDK_ROOT", ndk)
        environment.prepend_path("PATH", binaries)
        environment.unset("CROSS_SYSROOT")
        environment.unset("CROSS_COMPILE")
        toolchain.generate(environment)

    def build(self):
        perl = shlex.quote(self._required_tool("user.overte:perl_path"))
        make = shlex.quote(self._required_tool("user.overte:make_path"))
        configure = shlex.quote(os.path.join(self.source_folder, "Configure"))
        platform_config = os.path.join(self.build_folder, "overte-android.conf")
        # Qt's Android runtime resolver uses the OpenSSL-major suffix. Produce
        # that name and SONAME at the original link, not by copying/patching an
        # already-built provider. Upstream retains the development symlinks for
        # -lssl/-lcrypto; APK consumers must package only the canonical pair.
        save(self, platform_config, '''my %targets = (
    "overte-android-arm64" => {
        inherit_from => [ "android-arm64" ],
        shlib_variant => "_3",
    },
);
''')
        args = [
            "overte-android-arm64",
            "--config=" + shlex.quote(platform_config),
            "-D__ANDROID_API__=26",
            "shared",
            "no-docs",
            "no-fips",
            "no-module",
            "no-tests",
            "--prefix=/",
            "--openssldir=/etc/ssl",
            "--libdir=lib",
        ]
        self.run(f"{perl} {configure} {' '.join(args)}", env="conanbuild")
        self.run(f"{make} -j{build_jobs(self)}", env="conanbuild")

    def package(self):
        make = shlex.quote(self._required_tool("user.overte:make_path"))
        destination = shlex.quote(self.package_folder)
        self.run(f"{make} install_sw DESTDIR={destination}", env="conanbuild")
        copy(
            self,
            "LICENSE.txt",
            src=self.source_folder,
            dst=os.path.join(self.package_folder, "licenses"),
        )
        rmdir(self, os.path.join(self.package_folder, "bin"))

    def package_info(self):
        self.cpp_info.libs = ["ssl", "crypto"]
        # This recipe admits only Android: Bionic supplies pthread APIs in
        # libc, and the NDK has no separate libpthread to pass to consumers.
        self.cpp_info.system_libs = ["dl"]
        self.cpp_info.set_property("cmake_file_name", "OpenSSL")
        self.cpp_info.set_property("pkg_config_name", "openssl")
