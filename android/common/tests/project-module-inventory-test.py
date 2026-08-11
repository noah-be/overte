#!/usr/bin/env python3
"""Validate every Gradle Android module and its honest host/runtime boundary."""

import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
EXPECTED_MODULES = {
    "interface", "picoInterface", "questInterface", "framePlayer",
    "questFramePlayer", "qt", "oculus",
}
COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")
PRODUCT_BUILD_FILES = ("CMakeLists.txt", "build.gradle")


def fail(message):
    raise ValueError(message)


def parse_sdk(build):
    values = {}
    for key, pattern in {
        "compile": r"\bcompileSdk(?:Version)?\s*(?:=\s*)?(\d+)",
        "min": r"\bminSdk(?:Version)?\s*(?:=\s*)?(\d+)",
        "target": r"\btargetSdk(?:Version)?\s*(?:=\s*)?(\d+)",
    }.items():
        matches = re.findall(pattern, build)
        if len(set(matches)) != 1:
            fail(f"cannot determine one {key} SDK value")
        values[key] = int(matches[0])
    return values


def validate_application_security(name, module, build, manifest):
    actual_sdk = parse_sdk(build)
    if module.get("sdk") != actual_sdk:
        fail(f"{name} SDK baseline changed: {actual_sdk}")

    actual_permissions = [
        permission.get(ANDROID_NS + "name")
        for permission in manifest.findall("uses-permission")
    ]
    if None in actual_permissions:
        fail(f"{name} has an unnamed permission")
    actual_permissions.sort()
    if module.get("permissions") != actual_permissions:
        fail(f"{name} permission allowlist changed: {actual_permissions}")

    application = manifest.find("application")
    exported = []
    for tag in COMPONENT_TAGS:
        for component in application.findall(tag):
            component_name = component.get(ANDROID_NS + "name")
            if not component_name:
                fail(f"{name} has unnamed {tag}")
            declared = component.get(ANDROID_NS + "exported")
            if declared not in {None, "true", "false"}:
                fail(f"{name} {tag}:{component_name} has invalid exported value")
            has_filter = component.find("intent-filter") is not None
            if actual_sdk["target"] >= 31 and has_filter and declared is None:
                fail(f"{name} {tag}:{component_name} must explicitly declare exported")
            effective_exported = declared == "true" or (declared is None and has_filter)
            if effective_exported:
                exported.append(f"{tag}:{component_name}")
    exported.sort()
    if module.get("exportedComponents") != exported:
        fail(f"{name} exported component surface changed: {exported}")


def validate_sensitive_argument_logging(name, policy, root):
    if policy is None:
        return
    source_path = root / policy.get("source", "")
    identifiers = policy.get("identifiers")
    if not source_path.is_file() or not isinstance(identifiers, list) or not identifiers:
        fail(f"{name} sensitive-argument logging policy is stale")
    source = source_path.read_text(encoding="utf-8")
    for identifier in identifiers:
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z_$][\w$]*", identifier):
            fail(f"{name} has an invalid sensitive identifier")
        logging_call = re.compile(
            rf"(?:System\.(?:out|err)\.(?:print|println|printf)|Log\.[a-z]+)"
            rf"\s*\([^;]*\b{re.escape(identifier)}\b", re.DOTALL)
        if logging_call.search(source):
            fail(f"{name} logs sensitive launch argument {identifier}")


def validate_product_path_boundaries(product, sources):
    """Reject build-time source ownership that crosses sibling products."""
    forbidden_products = {
        "phoneInterface": ("picoInterface", "questInterface"),
    }
    for sibling in forbidden_products.get(product, ()):
        pattern = re.compile(
            rf"(?:\.\.[/\\]|apps[/\\]){re.escape(sibling)}[/\\]"
        )
        for source_name, source in sources.items():
            if pattern.search(source):
                fail(
                    f"{product} build file {source_name} directly references "
                    f"sibling product {sibling}"
                )


def main(repository):
    root = Path(repository).resolve()
    inventory = json.loads((root / "android/common/tests/project-module-inventory.json").read_text())
    phone_root = root / "android/phone/apps/phoneInterface"
    validate_product_path_boundaries(
        "phoneInterface",
        {
            name: (phone_root / name).read_text(encoding="utf-8")
            for name in PRODUCT_BUILD_FILES
        },
    )
    modules = inventory.get("modules")
    if not isinstance(modules, list):
        fail("module inventory requires a modules list")
    names = [module.get("name") for module in modules]
    if len(names) != len(set(names)) or set(names) != EXPECTED_MODULES:
        fail(f"module inventory mismatch: {names}")

    platform_settings = {
        "phoneInterface": (root / "android/phone/settings.gradle").read_text(encoding="utf-8"),
        "picoInterface": (root / "android/vr/pico/settings.gradle").read_text(encoding="utf-8"),
    }
    for module in modules:
        name = module["name"]
        module_root = root / module["path"]
        build_file = module_root / "build.gradle"
        manifest_file = module_root / "src/main/AndroidManifest.xml"
        if not build_file.is_file() or not manifest_file.is_file():
            fail(f"{name} lacks build.gradle or AndroidManifest.xml")
        settings = platform_settings.get(name)
        if settings is not None and f"include ':{name}'" not in settings:
            fail(f"{name} is absent from the platform settings.gradle files")

        build = build_file.read_text(encoding="utf-8")
        expected_plugin = f"com.android.{module['plugin']}"
        if expected_plugin not in build:
            fail(f"{name} does not apply {expected_plugin}")
        native_target = module.get("nativeTarget")
        if native_target and not re.search(
                rf"(?:targets\s*=\s*\[['\"]{re.escape(native_target)}['\"]\]|"
                rf"targets\s+['\"]{re.escape(native_target)}['\"])", build):
            fail(f"{name} does not declare native target {native_target}")

        manifest = ET.parse(manifest_file).getroot()
        application = manifest.find("application")
        expected_backup = module.get("allowBackup")
        if module["plugin"] == "application":
            if application is None:
                fail(f"{name} application manifest has no application element")
            actual_backup = application.get(ANDROID_NS + "allowBackup")
            if actual_backup not in {"true", "false"}:
                fail(f"{name} must explicitly declare allowBackup")
            if (actual_backup == "true") != expected_backup:
                fail(f"{name} allowBackup changed without inventory review")
            activities = application.findall("activity")
            native_values = {
                metadata.get(ANDROID_NS + "value")
                for activity in activities
                for metadata in activity.findall("meta-data")
                if metadata.get(ANDROID_NS + "name") == "android.app.lib_name"
            }
            if native_target not in native_values:
                fail(f"{name} manifest does not load {native_target}")
            validate_application_security(name, module, build, manifest)
            validate_sensitive_argument_logging(
                name, module.get("sensitiveArgumentLogging"), root)

        evidence = module.get("hostEvidence")
        if not evidence or any(not (root / path).is_file() for path in evidence):
            fail(f"{name} host evidence is empty or stale")
        boundary = module.get("runtimeBoundary")
        if not isinstance(boundary, str) or len(boundary) < 40:
            fail(f"{name} needs a concrete runtime-boundary rationale")

    print(f"Android project module inventory passed: {len(modules)} modules classified")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: project-module-inventory-test.py <repository-root>")
    main(sys.argv[1])
