#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/model-serializers/src/FBXWriter.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require("#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)\n"
        "    const int type = prop.metaType().id();" in SOURCE,
        "Qt 6 FBX property dispatch must use QVariant::metaType")
require("#else\n    const int type = prop.userType();" in SOURCE,
        "Qt 5 FBX property dispatch must retain userType")
require("QVariant::Type" not in SOURCE and "case QMetaType::Bool:" in SOURCE,
        "FBX bool dispatch must use the shared QMetaType id")

wire_cases = {
    "Short": "Y",
    "Bool": "C",
    "Int": "I",
    "Float": "F",
    "Double": "D",
    "LongLong": "L",
    "QString": "S",
    "QByteArray": "S",
}
for meta_type, tag in wire_cases.items():
    case = SOURCE.index(f"case QMetaType::{meta_type}:")
    next_case = SOURCE.find("case QMetaType::", case + 1)
    end = next_case if next_case >= 0 else SOURCE.index("default:", case)
    require(f'out.device()->write("{tag}", 1);' in SOURCE[case:end],
            f"FBX wire tag changed for {meta_type}")

for vector_type, tag in (("float", "f"), ("double", "d"), ("qint64", "l"), ("qint32", "i"), ("bool", "b")):
    require(f"writeVector(out, '{tag}', prop.value<QVector<{vector_type}>>())" in SOURCE,
            f"FBX vector wire tag changed for QVector<{vector_type}>")

print("FBXWriter Qt 6 QVariant contract valid: property and wire-tag semantics preserved")
