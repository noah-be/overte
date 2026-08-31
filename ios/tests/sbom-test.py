#!/usr/bin/env python3
"""Host contracts for deterministic iOS SBOM generation."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    path = IOS_ROOT / "tools/generate-sbom.py"
    specification = importlib.util.spec_from_file_location("generate_ios_sbom", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main() -> None:
    generator = load_generator()
    inventory = json.loads((IOS_ROOT / "dependencies.json").read_text(encoding="utf-8"))
    graph = {
        "graph": {
            "nodes": {
                "0": {"ref": "overte-ios-dependencies/0.1", "context": "host"},
                "1": {
                    "ref": "openssl/3.5.7#revision",
                    "context": "host",
                    "license": "Apache-2.0",
                },
                "2": {
                    "ref": "imath/3.1.9",
                    "context": "host",
                    "license": ["BSD-3-Clause"],
                },
                "3": {"ref": "scribe/2019.02@overte/stable", "context": "build"},
            }
        }
    }
    payload = generator.generate_sbom(graph, inventory)
    assert payload["bomFormat"] == "CycloneDX" and payload["specVersion"] == "1.6"
    assert [component["name"] for component in payload["components"]] == ["imath", "openssl"]
    openssl = next(component for component in payload["components"] if component["name"] == "openssl")
    assert openssl["licenses"] == [{"license": {"name": "Apache-2.0"}}]
    imath = next(component for component in payload["components"] if component["name"] == "imath")
    assert any(prop["value"] == "transitive" for prop in imath["properties"])
    metadata = {item["name"]: item["value"] for item in payload["metadata"]["properties"]}
    assert metadata["overte:ios:build-tools"] == "scribe/2019.02"
    assert "qt" in metadata["overte:ios:unresolved-direct"].split(",")

    with tempfile.TemporaryDirectory(prefix="overte-ios-sbom-") as temporary:
        first = Path(temporary) / "first.json"
        second = Path(temporary) / "second.json"
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        first.write_text(serialized, encoding="utf-8")
        second.write_text(
            json.dumps(generator.generate_sbom(graph, inventory), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        assert first.read_bytes() == second.read_bytes()
    print("PASS deterministic iOS SBOM tests")


if __name__ == "__main__":
    main()
