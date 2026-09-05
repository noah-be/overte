"""Android-specific dependency graph for the standalone PICO client.

The upstream Overte recipe currently describes a desktop installation and
therefore pulls OpenVR, Steamworks, Discord RPC, desktop SQL drivers and Qt
WebEngine into Android cross builds.  This recipe inherits its toolchain and
package-generation logic while limiting requirements to client libraries that
can be used by the standalone Android target.
"""

import importlib.util
from pathlib import Path

from conan.tools.cmake import CMakeDeps


_upstream_path = Path(__file__).resolve().parents[3] / "conanfile.py"
_spec = importlib.util.spec_from_file_location("overte_upstream_conanfile", _upstream_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class PicoOverte(_module.Overte):
    name = "OvertePico"

    def generate(self):
        # The dependency packages intentionally remain Debug packages, but an
        # Android release variant configures the native build as
        # RelWithDebInfo.  Emit metadata for both consumer configurations so
        # CMake does not discard every Conan include/library property behind a
        # $<CONFIG:Debug> expression during an unsigned release build.
        super().generate()
        release_deps = CMakeDeps(self)
        release_deps.configuration = "RelWithDebInfo"
        release_deps.generate()

    def requirements(self):
        self.requires("artery-font-format/1.0.1")
        self.requires("bullet3/3.25")
        self.requires("cgltf/1.14@overte/stable")
        self.requires("draco/1.3.5")
        self.requires("etc2comp/cci.20170424")
        self.requires("gifcreator/2016.11@overte/stable")
        self.requires(
            "glad/0.1.36@overte/experimental"
            "#9612a3032fecdd1d8781dfb1b2bd6dc6"
        )
        self.requires("gli/cci.20210515")
        self.requires("glslang/1.4.350.0")
        # Local recipe fixes the bundled c-ares feature detection for bionic.
        self.requires("libnode/22.22.3@overte/stable")
        self.requires("nlohmann_json/3.11.2")
        # Local recipe adds the bionic/Android portability guards required by
        # the legacy nvtt sources.
        self.requires("nvidia-texture-tools/2023.01@overte/stable")
        self.requires("onetbb/2021.10.0")
        self.requires("openexr/3.1.9")
        self.requires("openxr/1.1.46@overte/stable")
        self.requires("opus/1.5.2")
        self.requires("quazip/1.4")
        self.requires("scribe/2019.02@overte/stable")
        self.requires("spirv-cross/1.4.350.0")
        self.requires("spirv-tools/1.4.350.0")
        self.requires("v-hacd/4.1.0")
        self.requires("vulkan-memory-allocator/3.0.1")
        self.requires("webrtc-audio-processing/2.1@overte/stable")
        self.requires("zlib/1.3.1")
        self.requires("glm/0.9.9.5", force=True)
        self.requires("jsoncpp/1.9.6", force=True)
        self.requires(
            "qt/5.15.18-2026.01.04@overte/stable"
            "#c615fd9bf2e6410b92a3e6b84fa73980",
            force=True,
        )
        self.requires("openssl/3.5.8@overte/stable", force=True)
