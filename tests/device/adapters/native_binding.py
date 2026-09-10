"""Fixed, source-owned native extension of the canonical adapter entrypoints."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import importlib.util
from pathlib import Path
import sys

ADAPTER_ROOT = Path(__file__).resolve().parent
BINDINGS = {"phone": "android-phone", "pico": "pico4", "ios": "ios"}


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "OVT_ADAPTER_ARGUMENTS_REJECTED\n")


def attach_binding(parser, product, argv=None):
    """Parse ordinary fields first; only a fixed owned module can extend them."""
    mode_parser = PrivateParser(add_help=False, allow_abbrev=False)
    mode_parser.add_argument("--native-binding", action="store_true")
    provisional, _ = mode_parser.parse_known_args(argv)
    if not provisional.native_binding:
        return parser.parse_args(argv), None
    if product not in BINDINGS:
        raise ValueError("OVT_NATIVE_BINDING_PRODUCT_REJECTED")
    directory = ADAPTER_ROOT / BINDINGS[product]
    path = directory / "binding.py"
    if directory.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError("OVT_NATIVE_BINDING_UNAVAILABLE")
    # There is no command-line/environment module path, import search, or binary
    # plugin fallback. Source provenance must include this exact native file.
    spec = importlib.util.spec_from_file_location("overte_native_binding_" + product, path)
    module = importlib.util.module_from_spec(spec)
    source = path.read_bytes()
    if len(source) > 1024 * 1024:
        raise ValueError("OVT_NATIVE_BINDING_SOURCE_SIZE")
    # Read the actual pinned Python source, never a stale/foreign .pyc cache.
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
        raise
    if not callable(getattr(module, "configure_parser", None)) or not callable(getattr(module, "create_adapter", None)):
        raise ValueError("OVT_NATIVE_BINDING_INTERFACE_REJECTED")
    protected = tuple((action.dest, tuple(action.option_strings), action.required,
                       action.nargs, action.default, action.choices, action.type)
                      for action in parser._actions)
    module.configure_parser(parser)
    shared_destinations = {action[0] for action in protected}
    if any(action.dest in shared_destinations for action in parser._actions[len(protected):]):
        raise ValueError("OVT_NATIVE_BINDING_SHARED_ARGUMENT_MUTATION")
    current = tuple((action.dest, tuple(action.option_strings), action.required,
                     action.nargs, action.default, action.choices, action.type)
                    for action in parser._actions[:len(protected)])
    if protected != current:
        raise ValueError("OVT_NATIVE_BINDING_SHARED_ARGUMENT_MUTATION")
    args = parser.parse_args(argv)
    if not args.native_binding:
        raise ValueError("OVT_NATIVE_BINDING_MODE_CHANGED")
    return args, module


def create_adapter(args, module, base_class, kind):
    if module is None:
        return base_class(kind)
    adapter = module.create_adapter(args, base_class)
    if not isinstance(adapter, base_class):
        raise ValueError("OVT_NATIVE_BINDING_BASE_REJECTED")
    return adapter
