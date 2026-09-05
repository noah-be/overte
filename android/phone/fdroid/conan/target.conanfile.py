"""Bound Android target graph with separately resolved Linux host tools."""

import importlib.util
from pathlib import Path


_pico_recipe = Path(__file__).resolve().parents[4] / "android/common/conan/conanfile-pico.py"
_spec = importlib.util.spec_from_file_location("overte_pico_target", _pico_recipe)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class OverteAndroidTarget(_module.PicoOverte):
    name = "OverteAndroidSourceTarget"
    default_options = dict(_module.PicoOverte.default_options)
    default_options.update(
        {
            "qt*:qtwebengine": False,
            "qt*:with_mysql": False,
            "qt*:with_odbc": False,
            "qt*:with_openal": False,
            "qt*:with_pq": False,
        }
    )

    def build_requirements(self):
        self.tool_requires(
            "qt/5.15.18-2026.01.04@overte/stable"
            "#c615fd9bf2e6410b92a3e6b84fa73980",
            run=True,
        )
        self.tool_requires("glslang/1.4.350.0", run=True)
        self.tool_requires("scribe/2019.02@overte/stable", run=True)
        self.tool_requires("spirv-cross/1.4.350.0", run=True)
        self.tool_requires("spirv-tools/1.4.350.0", run=True)
