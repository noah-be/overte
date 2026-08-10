#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/entities/src/EntityDynamicInterface.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require("bool isVariantMap(const QVariant& value)" in SOURCE,
        "dynamic argument parsing must centralize its QVariant map check")
require("#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)" in SOURCE and
        "value.metaType().id() == QMetaType::QVariantMap" in SOURCE,
        "Qt 6 must inspect QVariant through QMetaType")
require("#else\n    return value.type() == QVariant::Map;" in SOURCE,
        "the retained Qt 5 build must preserve its exact map-type check")
require(SOURCE.count("if (!isVariantMap(resultV))") == 2,
        "vec3 and quaternion dynamic arguments must share the strict map check")
require("resultV.type() !=" not in SOURCE,
        "EntityDynamicInterface retained a direct removed QVariant::type comparison")
require("canConvert<QVariantMap>" not in SOURCE,
        "the migration must not broaden accepted dynamic argument types")

print("EntityDynamicInterface Qt 6 QVariant contract valid: strict map semantics preserved")
