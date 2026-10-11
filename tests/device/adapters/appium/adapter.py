#!/usr/bin/env python3
"""Shared Appium entrypoint with optional, fixed product-owned iOS routing."""
import importlib
from pathlib import Path
import sys

DEVICE_ROOT = Path(__file__).resolve().parents[2]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))
from adapters.shared_appium.adapter import AppiumAdapter, WebDriver, main as shared_main  # noqa: E402,F401
from adapters.native_binding import PrivateParser  # noqa: E402


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    selector = PrivateParser(add_help=False, allow_abbrev=False)
    selector.add_argument("--platform", choices=("android", "ios"))
    platform, _ = selector.parse_known_args(arguments)
    if platform.platform == "ios":
        try:
            native = importlib.import_module("ios.adapters.appium_adapter")
        except ModuleNotFoundError as error:
            if error.name not in {"ios.adapters", "ios.adapters.appium_adapter"}:
                raise
        else:
            return native.main(arguments)
    if "--native-binding" in arguments:
        raise ValueError("OVT_NATIVE_BINDING_PRODUCT_REJECTED")
    original = sys.argv
    try:
        sys.argv = [original[0], *arguments]
        return shared_main()
    finally:
        sys.argv = original

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        if "--native-binding" in sys.argv:
            print("OVT_APPIUM_ADAPTER_REJECTED", file=sys.stderr)
        else:
            print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
