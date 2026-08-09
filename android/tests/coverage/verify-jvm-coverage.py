#!/usr/bin/env python3
"""Enforce coverage only for framework-independent Phone policy classes."""

import sys
import xml.etree.ElementTree as ET


CRITICAL_CLASSES = {
    "io/highfidelity/utils/SafeAssetPath",
    "org/overte/phone/PhoneDeepLinkNormalizer",
    "org/overte/phone/PhoneLaunchState",
    "org/overte/phone/PhonePendingUrlPolicy",
    "org/overte/phone/PhonePermissionFlow",
}
REQUIRED_COUNTER_PERCENT = {
    "LINE": 100.0,
    "BRANCH": 100.0,
}


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    counters = {}
    for class_node in root.findall(".//class"):
        name = class_node.attrib.get("name")
        if name not in CRITICAL_CLASSES:
            continue
        counters[name] = {
            counter.attrib["type"]: (int(counter.attrib["covered"]),
                                     int(counter.attrib["missed"]))
            for counter in class_node.findall("counter")
        }
    missing = CRITICAL_CLASSES - counters.keys()
    if missing:
        print("Missing critical coverage classes: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1
    failed = False
    for counter_type, minimum in REQUIRED_COUNTER_PERCENT.items():
        covered = sum(value[counter_type][0] for value in counters.values())
        missed = sum(value[counter_type][1] for value in counters.values())
        percentage = covered * 100.0 / (covered + missed)
        print(f"Critical Phone JVM {counter_type.lower()} coverage: "
              f"{covered}/{covered + missed} ({percentage:.2f}%)")
        if percentage < minimum:
            print(f"Required {counter_type.lower()} minimum is {minimum:.2f}%",
                  file=sys.stderr)
            failed = True
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
