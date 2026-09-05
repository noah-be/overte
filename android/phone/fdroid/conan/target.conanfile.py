"""Bound Android target graph with separately resolved Linux host tools."""

import importlib.util
from pathlib import Path


_pico_recipe = Path(__file__).resolve().parents[4] / "android/common/conan/conanfile-pico.py"
_spec = importlib.util.spec_from_file_location("overte_pico_target", _pico_recipe)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class OverteAndroidTarget(_module.PicoOverte):
    name = "OverteAndroidSourceTarget"
    qt_ref = (
        "qt/5.15.18-2026.01.04@overte/stable"
        "#067e63fa931d764bcb1e93004544cf4f"
    )
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
            "#067e63fa931d764bcb1e93004544cf4f",
            run=True,
        )
        self.tool_requires("glslang/1.4.350.0", run=True)
        self.tool_requires("scribe/2019.02@overte/stable", run=True)
        self.tool_requires("spirv-cross/1.4.350.0", run=True)
        self.tool_requires("spirv-tools/1.4.350.0", run=True)
