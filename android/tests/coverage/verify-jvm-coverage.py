#!/usr/bin/env python3
"""Enforce coverage for the explicitly scoped framework-independent JVM policies."""

import sys
import xml.etree.ElementTree as ET


CRITICAL_CLASSES = {
    "io/highfidelity/hifiinterface/HifiUtils",
    "org/overte/pico/AndroidAudioInputPolicy",
    "org/overte/pico/PicoInterfaceActivityPolicy",
    "org/overte/pico/PicoActivityInstancePolicy",
    "io/highfidelity/utils/AssetCacheExtractor",
    "io/highfidelity/utils/SafeAssetPath",
    "org/overte/phone/PhoneDeepLinkNormalizer",
    "org/overte/phone/PhoneLaunchState",
    "org/overte/phone/PhonePendingUrlPolicy",
    "org/overte/phone/PhonePermissionFlow",
}
CLASS_MINIMUMS = {
    name: {"LINE": 100.0, "BRANCH": 100.0} for name in CRITICAL_CLASSES
}
# The only remaining extractor branch is a filesystem race: mkdirs() loses to
# another creator and the directory exists by the subsequent isDirectory().
# Reproducing that nondeterministically would make the clean-host gate flaky.
CLASS_MINIMUMS["io/highfidelity/utils/AssetCacheExtractor"] = {
    "LINE": 100.0,
    "BRANCH": 95.0,
}


def main(path: str) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        print(f"Invalid JVM coverage report: {error}", file=sys.stderr)
        return 1
    counters = {}
    for class_node in root.findall(".//class"):
        name = class_node.attrib.get("name")
        if name not in CRITICAL_CLASSES:
            continue
        if name in counters:
            print(f"Duplicate critical coverage class: {name}", file=sys.stderr)
            return 1
        try:
            counters[name] = {
                counter.attrib["type"]: (int(counter.attrib["covered"]),
                                         int(counter.attrib["missed"]))
                for counter in class_node.findall("counter")
            }
        except (KeyError, ValueError):
            print(f"Invalid coverage counters for {name}", file=sys.stderr)
            return 1
    missing = CRITICAL_CLASSES - counters.keys()
    if missing:
        print("Missing critical coverage classes: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1
    failed = False
    for name in sorted(CRITICAL_CLASSES):
        for counter_type, minimum in CLASS_MINIMUMS[name].items():
            if counter_type not in counters[name]:
                print(f"Missing {counter_type.lower()} counter for {name}", file=sys.stderr)
                failed = True
                continue
            covered, missed = counters[name][counter_type]
            if covered < 0 or missed < 0 or covered + missed == 0:
                print(f"Invalid {counter_type.lower()} counter for {name}", file=sys.stderr)
                failed = True
                continue
            percentage = covered * 100.0 / (covered + missed)
            print(f"{name} {counter_type.lower()} coverage: "
                  f"{covered}/{covered + missed} ({percentage:.2f}%)")
            if percentage < minimum:
                print(f"Required {name} {counter_type.lower()} minimum is "
                      f"{minimum:.2f}%", file=sys.stderr)
                failed = True
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
