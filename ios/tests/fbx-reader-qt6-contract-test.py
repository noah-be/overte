#!/usr/bin/env python3
"""Regression contract for Qt 6 FBX parsing and serverless model evidence."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERIALIZER = (ROOT / "libraries/model-serializers/src/FBXSerializer.cpp").read_text(encoding="utf-8")
MESH_SERIALIZER = (ROOT / "libraries/model-serializers/src/FBXSerializer_Mesh.cpp").read_text(encoding="utf-8")
MODEL_TEST = (ROOT / "tests/model-serializers/src/ModelSerializersTests.cpp").read_text(encoding="utf-8")
MODEL_RENDERER = (ROOT / "libraries/entities-renderer/src/RenderableModelEntityItem.cpp").read_text(encoding="utf-8")
TEXT_RENDERER = (ROOT / "libraries/entities-renderer/src/RenderableTextEntityItem.cpp").read_text(encoding="utf-8")
FIXTURE = ROOT / "interface/resources/serverless/Models/standAngle.fbx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require(FIXTURE.is_file() and FIXTURE.stat().st_size > 0,
        "the actual missing serverless FBX fixture is unavailable")
require('object.properties.at(2).toByteArray() == "Mesh"' in SERIALIZER,
        "Qt 6 would discard FBX Geometry/Mesh nodes")
for token in ("LimbNode", "Cluster", "BlendShapeChannel"):
    require(f'toByteArray() == "{token}"' in SERIALIZER,
            f"Qt 6 FBX {token} comparison is not byte-array explicit")
for token in ("BY_VERTICE", "INDEX_TO_DIRECT", "BY_POLYGON"):
    require(f"toByteArray() == {token}" in MESH_SERIALIZER,
            f"Qt 6 FBX mesh mapping comparison is not byte-array explicit: {token}")

# QVariant stopped providing the implicit comparison behavior relied on by the
# Qt 5 reader. Direct comparisons on FBX property variants must not return.
legacy_comparison = re.compile(r"properties\.(?:at\([^)]*\)|last\(\))\s*[!=]=\s*(?!QVariant)")
for name, source in (("FBXSerializer.cpp", SERIALIZER), ("FBXSerializer_Mesh.cpp", MESH_SERIALIZER)):
    code_without_line_comments = re.sub(r"//.*", "", source)
    matches = [match.group(0) for match in legacy_comparison.finditer(code_without_line_comments)
               if ".toByteArray()" not in code_without_line_comments[match.start():match.start() + 90]]
    require(not matches, f"{name} still has implicit Qt 5 QVariant comparisons: {matches[:3]}")

fst_files = list((ROOT / "interface/resources/serverless/Models").glob("standAngle_*.fst"))
require(len(fst_files) == 5,
        "expected all five missing tutorial information stands")
for fst in fst_files:
    require("filename = qrc:///serverless/Models/standAngle.fbx" in fst.read_text(encoding="utf-8"),
            f"{fst.name} no longer exercises standAngle.fbx")

require("void ModelSerializersTests::loadFBX()" in MODEL_TEST and
        '"../../../interface/resources/serverless/Models/standAngle.fbx"' in MODEL_TEST and
        "!model->meshes.empty()" in MODEL_TEST,
        "native regression test does not parse and verify the affected FBX")
require("OVERTE_IOS_MODEL_GATE stage=url-finished" in MODEL_RENDERER and
        '"hfm_meshes="' in MODEL_RENDERER and
        "OVERTE_IOS_MODEL_GATE stage=scene-added" in MODEL_RENDERER,
        "device logs cannot isolate FBX parsing from scene handoff")
require("!args->_shapePipeline" in TEXT_RENDERER,
        "upstream Qt 6 text-fade null-pipeline crash guard is missing")

print("Qt 6 FBX reader contract valid: standAngle geometry retained, natively tested, and observable on device")
