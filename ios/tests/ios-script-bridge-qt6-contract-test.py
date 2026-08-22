#!/usr/bin/env python3
"""Contract checks for the Qt 6/V8 QObject bridge used by iOS scripts."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROXY_HEADER = ROOT / "libraries/script-engine/src/v8/ScriptObjectV8Proxy.h"
PROXY_SOURCE = ROOT / "libraries/script-engine/src/v8/ScriptObjectV8Proxy.cpp"
SCRIPT_MANAGER = ROOT / "libraries/script-engine/src/ScriptManager.cpp"
ENTITY_INTERFACE = ROOT / "libraries/entities/src/EntityScriptingInterface.cpp"
INTERFACE_CMAKE = ROOT / "interface/CMakeLists.txt"
INTERFACE_MAIN = ROOT / "interface/src/main.cpp"
SCRIPT_TEST = ROOT / "tests/script-engine/src/ScriptEngineTests.cpp"
NETWORKED_TEST = ROOT / "tests/script-engine/src/ScriptEngineNetworkedTests.cpp"
WIZARD_LOADER = ROOT / "interface/resources/serverless/Scripts/wizardLoader.js"
WIZARD_QML = ROOT / "interface/resources/serverless/Scripts/Wizard.qml"


def test_name_lookup_maps_do_not_retain_qhash_value_pointers() -> None:
    header = PROXY_HEADER.read_text(encoding="utf-8")
    source = PROXY_SOURCE.read_text(encoding="utf-8")

    for definition in ("PropertyDef", "MethodDef", "SignalDef"):
        assert f"QHash<QString, {definition}>" in header
        assert f"QHash<QString, {definition}*>" not in header
    for insertion in (
        "_propNameMap.insert(prop.name(), propDef)",
        "_methodNameMap.insert(szName, methodDef)",
        "_signalNameMap.insert(szName, signalDef)",
    ):
        assert insertion in source


def test_qt6_invocation_uses_the_formal_moc_parameter_name() -> None:
    source = PROXY_SOURCE.read_text(encoding="utf-8")

    assert "const char* argumentTypeName = meta.parameterTypeName(arg);" in source
    assert "QGenericArgument(argumentTypeName, const_cast<void*>(converted.constData()))" in source
    assert "qVarArgLists[i].emplace_back();" in source


def test_device_logs_expose_script_api_readiness() -> None:
    script_manager = SCRIPT_MANAGER.read_text(encoding="utf-8")
    entity_interface = ENTITY_INTERFACE.read_text(encoding="utf-8")

    assert "OVERTE_IOS_SCRIPT_API_GATE" in script_manager
    for method in ("require", "load", "include", "setInterval", "fromVec3Degrees"):
        assert f'.property("{method}").isFunction()' in script_manager
    assert "OVERTE_IOS_ENTITY_SCRIPT_API_GATE" in entity_interface
    for method in ("getEntityProperties", "addEntity", "getMultipleEntityProperties"):
        assert f'.property("{method}").isFunction()' in entity_interface


def test_static_qml_plugins_are_imported_and_reported_on_ios() -> None:
    cmake = INTERFACE_CMAKE.read_text(encoding="utf-8")
    main = INTERFACE_MAIN.read_text(encoding="utf-8")

    assert "if(IOS AND OVERTE_QT_MAJOR EQUAL 6)" in cmake
    assert "add_library(overte-ios-qml-plugin-imports INTERFACE)" in cmake
    assert "qt6_import_qml_plugins(overte-ios-qml-plugin-imports)" in cmake
    assert "target_link_libraries(${TARGET_NAME} overte-ios-qml-plugin-imports)" in cmake
    assert "qt6_import_qml_plugins(${TARGET_NAME})" not in cmake
    assert "OVERTE_IOS_QML_PLUGIN_GATE" in main
    for plugin in (
        "QtQuick2Plugin",
        "QtQuickControls2Plugin",
        "QtQuickTemplates2Plugin",
        "QtQuickLayoutsPlugin",
        "QtQmlModelsPlugin",
    ):
        assert plugin in main


def test_runtime_regressions_cover_the_observed_ipad_failures() -> None:
    script_test = SCRIPT_TEST.read_text(encoding="utf-8")
    networked_test = NETWORKED_TEST.read_text(encoding="utf-8")

    assert "testScriptApiMethodDiscovery" in script_test
    assert "Quat.fromVec3Degrees({ x: -58, y: 0, z: 0 })" in script_test
    assert "testEntityApiMethodDiscovery" in networked_test
    assert "typeof Entities.getEntityProperties" in networked_test

    wizard_loader = WIZARD_LOADER.read_text(encoding="utf-8")
    wizard_qml = WIZARD_QML.read_text(encoding="utf-8")
    assert "OVERTE_IOS_WIZARD_GATE stage=entity-created" in wizard_loader
    assert 'Entities.getEntityProperties(' in wizard_loader
    assert 'import "qrc:/qml/styles" as HifiStyles' in wizard_qml
    assert 'import "qrc:/qml/hifi" as Hifi' in wizard_qml
    assert "qrc:////" not in wizard_qml
    assert "OVERTE_IOS_WIZARD_QML_GATE stage=component-completed" in wizard_qml


if __name__ == "__main__":
    test_name_lookup_maps_do_not_retain_qhash_value_pointers()
    test_qt6_invocation_uses_the_formal_moc_parameter_name()
    test_device_logs_expose_script_api_readiness()
    test_static_qml_plugins_are_imported_and_reported_on_ios()
    test_runtime_regressions_cover_the_observed_ipad_failures()
    print("iOS Qt 6 script bridge contract checks passed")
