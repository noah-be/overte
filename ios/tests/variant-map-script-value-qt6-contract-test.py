#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/script-engine/src/VariantMapToScriptValue.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require("#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)\n"
        "    const int variantType = qValue.metaType().id();" in SOURCE,
        "Qt 6 must read QVariant's QMetaType id")
require("#else\n    const int variantType = qValue.userType();" in SOURCE,
        "Qt 5 must retain a compatible metatype-id path")
require("switch (variantType)" in SOURCE and "switch(qValue.type())" not in SOURCE,
        "the converter must not switch on removed QVariant::type()")
for case in ("Bool", "Int", "Double", "QString", "QUrl", "QVariantMap", "QVariantList"):
    require(f"case QMetaType::{case}:" in SOURCE, f"missing preserved QVariant conversion case: {case}")
require("if (qValue.canConvert<float>())" in SOURCE and
        "return scriptEngine.newValue(qValue.toFloat());" in SOURCE,
        "the numeric compatibility fallback must remain unchanged")

print("VariantMapToScriptValue Qt 6 contract valid: QMetaType switch with Qt 5 fallback")
