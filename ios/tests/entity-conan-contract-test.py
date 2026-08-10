#!/usr/bin/env python3
"""Host tests for the direct entity-to-Conan contract audit."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = IOS_ROOT.parent


def load_auditor():
    path = IOS_ROOT / "tools" / "audit-entity-conan-contract.py"
    specification = importlib.util.spec_from_file_location("audit_entity_conan_contract", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def expect_rejected(auditor, discovered, inventory, recipe, expected: str) -> None:
    try:
        auditor.validate_contract(discovered, inventory, recipe)
    except ValueError as error:
        assert expected in str(error), error
    else:
        raise AssertionError(f"contract was accepted; expected {expected}")


def main() -> None:
    auditor = load_auditor()
    count, discovered = auditor.audit(SOURCE_ROOT)
    assert count == 4
    assert discovered == {
        "networking": {"glm", "onetbb", "openssl"},
        "octree": {"glm"},
        "entities": {"glm", "openssl"},
        "entities-renderer": {"bullet3", "glm"},
    }

    inventory = {
        "dependencies": {
            package: {"class": "required", "ship": True}
            for package in {"glm", "onetbb", "openssl", "bullet3"}
        }
    }
    recipe = {"glm", "onetbb", "openssl", "bullet3"}
    assert auditor.validate_contract(discovered, inventory, recipe) == 4

    missing_recipe = recipe - {"openssl"}
    expect_rejected(auditor, discovered, inventory, missing_recipe, "absent from staged Conan recipe: openssl")
    disabled = {"dependencies": dict(inventory["dependencies"])}
    disabled["dependencies"]["bullet3"] = {"class": "disabled", "ship": False}
    expect_rejected(auditor, discovered, disabled, recipe, "not an enabled target package: bullet3")
    print("PASS direct iOS entity Conan contract tests")


if __name__ == "__main__":
    main()
