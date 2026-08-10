#!/usr/bin/env python3
"""Audit direct external requirements of the staged iOS entity pipeline."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


TARGETS = ("networking", "octree", "entities", "entities-renderer")
MACRO_PACKAGES = {
    "target_openssl": "openssl",
    "target_tbb": "onetbb",
    "target_bullet": "bullet3",
}
HEADER_PACKAGES = {
    "openssl/": "openssl",
    "tbb/": "onetbb",
    "oneapi/tbb/": "onetbb",
    "glm/": "glm",
}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".in", ".mm"}


def recipe_requirements(recipe_text: str) -> set[str]:
    return set(re.findall(r'self\.requires\(["\']([^/"\']+)/', recipe_text))


def discover_target_requirements(source_root: Path) -> dict[str, set[str]]:
    discovered: dict[str, set[str]] = {}
    for target in TARGETS:
        target_root = source_root / "libraries" / target
        cmake = (target_root / "CMakeLists.txt").read_text(encoding="utf-8")
        packages = {
            package
            for macro, package in MACRO_PACKAGES.items()
            if re.search(rf"\b{re.escape(macro)}\s*\(", cmake)
        }
        for path in target_root.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            includes = re.findall(r'^\s*#\s*include\s*[<"]([^>"]+)', text, re.MULTILINE)
            for include in includes:
                for prefix, package in HEADER_PACKAGES.items():
                    if include.startswith(prefix):
                        packages.add(package)
        discovered[target] = packages
    return discovered


def validate_contract(
    discovered: dict[str, set[str]], inventory: dict, recipe_packages: set[str]
) -> int:
    if set(discovered) != set(TARGETS):
        raise ValueError("entity dependency scan did not cover exactly the four staged targets")
    dependencies = inventory.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ValueError("iOS dependency inventory has no dependencies object")

    direct = set().union(*discovered.values())
    if not direct:
        raise ValueError("entity dependency scan found no direct Conan requirements")
    for package in sorted(direct):
        policy = dependencies.get(package)
        if not isinstance(policy, dict):
            raise ValueError(f"direct entity dependency is unclassified: {package}")
        if policy.get("class") not in {"required", "required-audit"} or policy.get("ship") is not True:
            raise ValueError(f"direct entity dependency is not an enabled target package: {package}")
        if package not in recipe_packages:
            targets = sorted(target for target, packages in discovered.items() if package in packages)
            raise ValueError(f"direct entity dependency is absent from staged Conan recipe: {package} ({', '.join(targets)})")
    return len(direct)


def audit(source_root: Path) -> tuple[int, dict[str, set[str]]]:
    ios_root = source_root / "ios"
    inventory = json.loads((ios_root / "dependencies.json").read_text(encoding="utf-8"))
    recipe = (ios_root / "conanfile.py").read_text(encoding="utf-8")
    discovered = discover_target_requirements(source_root)
    return validate_contract(discovered, inventory, recipe_requirements(recipe)), discovered


def main() -> int:
    source_root = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path(__file__).resolve().parents[2]
    if len(sys.argv) > 2:
        print(f"usage: {sys.argv[0]} [SOURCE_ROOT]", file=sys.stderr)
        return 2
    try:
        count, discovered = audit(source_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    details = "; ".join(f"{target}={','.join(sorted(packages))}" for target, packages in discovered.items())
    print(f"Verified {count} direct iOS entity Conan packages: {details}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
