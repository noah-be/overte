#!/usr/bin/env python3

import pathlib
import sys
import xml.etree.ElementTree as ET


EXPECTED_DOMAINS = {
    "root",
    "file",
    "database",
    "sharedpref",
    "external",
    "device_root",
    "device_file",
    "device_database",
    "device_sharedpref",
}
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
EXPECTED_PERMISSIONS = {
    "android.permission.INTERNET",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.RECORD_AUDIO",
    "android.permission.MODIFY_AUDIO_SETTINGS",
    "android.permission.VIBRATE",
}
EXPECTED_ACTIVITIES = {
    ".PermissionsActivity": "true",
    ".PhoneInterfaceActivity": "false",
}
EXPECTED_DEEP_LINK_SCHEMES = {"overte", "hifi"}


def exclusions(element):
    rules = element.findall("exclude")
    domains = {rule.get("domain") for rule in rules if rule.get("path") == "."}
    return rules, domains


def require_complete_exclusions(element, label):
    rules, domains = exclusions(element)
    if len(rules) != len(EXPECTED_DOMAINS) or domains != EXPECTED_DOMAINS:
        missing = sorted(EXPECTED_DOMAINS - domains)
        unexpected = sorted(domains - EXPECTED_DOMAINS)
        raise ValueError(
            f"{label} is not fail-closed: missing={missing}, unexpected={unexpected}, "
            f"rules={len(rules)}"
        )
    if element.findall("include"):
        raise ValueError(f"{label} contains an unexpected backup include rule")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: phone-data-protection-test.py <android-root>")
    android_root = pathlib.Path(sys.argv[1])
    resource_root = android_root / "phone/apps/phoneInterface/src/main/res/xml"

    manifest = ET.parse(
        android_root / "phone/apps/phoneInterface/src/main/AndroidManifest.xml"
    ).getroot()
    application = manifest.find("application")
    if application is None:
        raise ValueError("phone manifest has no application element")
    expected_attributes = {
        "allowBackup": "false",
        "fullBackupContent": "@xml/backup_rules",
        "dataExtractionRules": "@xml/data_extraction_rules",
    }
    for name, expected in expected_attributes.items():
        actual = application.get(ANDROID_NS + name)
        if actual != expected:
            raise ValueError(f"manifest {name}={actual!r}, expected {expected!r}")
    if application.get(ANDROID_NS + "backupAgent") is not None:
        raise ValueError("phone manifest installs a custom backup agent")

    permissions = {
        element.get(ANDROID_NS + "name") for element in manifest.findall("uses-permission")
    }
    if permissions != EXPECTED_PERMISSIONS:
        raise ValueError(
            "phone permissions differ from the minimal allowlist: "
            f"missing={sorted(EXPECTED_PERMISSIONS - permissions)}, "
            f"unexpected={sorted(permissions - EXPECTED_PERMISSIONS)}"
        )

    activities = {
        element.get(ANDROID_NS + "name"): element.get(ANDROID_NS + "exported")
        for element in application.findall("activity")
    }
    if activities != EXPECTED_ACTIVITIES:
        raise ValueError(
            "phone activities differ from the export allowlist: "
            f"actual={activities!r}"
        )
    for component_type in ("activity-alias", "provider", "receiver", "service"):
        if application.findall(component_type):
            raise ValueError(f"phone manifest unexpectedly declares {component_type}")

    activity_elements = {
        element.get(ANDROID_NS + "name"): element
        for element in application.findall("activity")
    }
    launcher = activity_elements[".PermissionsActivity"]
    interface = activity_elements[".PhoneInterfaceActivity"]
    if launcher.get(ANDROID_NS + "launchMode") != "singleTop":
        raise ValueError("exported permission launcher must remain singleTop")
    if interface.get(ANDROID_NS + "launchMode") != "singleTask":
        raise ValueError("internal Qt activity must remain singleTask")

    filters = launcher.findall("intent-filter")
    view_filters = []
    launcher_filters = []
    for intent_filter in filters:
        actions = {
            item.get(ANDROID_NS + "name") for item in intent_filter.findall("action")
        }
        categories = {
            item.get(ANDROID_NS + "name") for item in intent_filter.findall("category")
        }
        if "android.intent.action.VIEW" in actions:
            view_filters.append((intent_filter, actions, categories))
        if "android.intent.action.MAIN" in actions:
            launcher_filters.append((actions, categories))
    if len(view_filters) != 1 or len(launcher_filters) != 1:
        raise ValueError("permission launcher needs exactly one MAIN and one VIEW filter")
    main_actions, main_categories = launcher_filters[0]
    if main_actions != {"android.intent.action.MAIN"} or main_categories != {
        "android.intent.category.LAUNCHER"
    }:
        raise ValueError("launcher filter actions/categories are not minimal")
    _, actions, categories = view_filters[0]
    if actions != {"android.intent.action.VIEW"} or categories != {
        "android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"
    }:
        raise ValueError("deep-link filter actions/categories are not fail-closed")
    schemes = {
        item.get(ANDROID_NS + "scheme")
        for item in view_filters[0][0].findall("data")
    }
    if schemes != EXPECTED_DEEP_LINK_SCHEMES:
        raise ValueError(
            f"deep-link schemes differ from allowlist: actual={sorted(schemes)}"
        )
    if interface.findall("intent-filter"):
        raise ValueError("internal Qt activity must not expose intent filters")

    legacy = ET.parse(resource_root / "backup_rules.xml").getroot()
    if legacy.tag != "full-backup-content":
        raise ValueError("legacy backup rules have the wrong root element")
    require_complete_exclusions(legacy, "legacy full backup")

    modern = ET.parse(resource_root / "data_extraction_rules.xml").getroot()
    if modern.tag != "data-extraction-rules":
        raise ValueError("modern extraction rules have the wrong root element")
    cloud = modern.find("cloud-backup")
    transfer = modern.find("device-transfer")
    if cloud is None or transfer is None:
        raise ValueError("modern rules must cover cloud backup and device transfer")
    require_complete_exclusions(cloud, "cloud backup")
    require_complete_exclusions(transfer, "device transfer")

    print("Android phone backup, permissions, and exported-component contracts passed.")


if __name__ == "__main__":
    main()
