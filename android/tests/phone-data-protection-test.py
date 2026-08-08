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
    resource_root = android_root / "apps/phoneInterface/src/main/res/xml"

    manifest = ET.parse(
        android_root / "apps/phoneInterface/src/main/AndroidManifest.xml"
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
