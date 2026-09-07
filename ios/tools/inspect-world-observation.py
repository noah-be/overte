#!/usr/bin/env python3
"""Retain the native bounded observation, never a world acceptance receipt."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os
from pathlib import Path
import re
import sys

BASE = {"schemaVersion", "status", "sourceBinding", "artifactBinding", "foreground",
        "armed", "committed", "capacityExceeded", "expectedEntities", "renderableEntities",
        "sceneEntities", "drawnEntities", "producer", "elapsedMs", "expired"}
FRAME = {"generation", "acceptedPresentCalls", "rejectedPresentCalls",
         "lastPresentedFrame", "softwareQmlImagesProduced"}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate observation field")
        result[key] = value
    return result


def inspect(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("observation unavailable")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if not 0 < len(raw) <= 4096:
        raise ValueError("observation size")
    sample = json.loads(raw, object_pairs_hook=unique)
    if type(sample) is not dict:
        raise ValueError("observation object")
    producer = sample.get("producer")
    fields = BASE | FRAME if producer == "generation-present-v1" else BASE
    if producer not in {"generation-present-v1", "entity-counts-only"} or set(sample) != fields:
        raise ValueError("observation fields")
    if type(sample["schemaVersion"]) is not int or sample["schemaVersion"] != 1 or \
            sample["status"] != "OBSERVATION_NOT_ACCEPTANCE" or \
            sample["sourceBinding"] != "EXTERNAL_CANDIDATE_REQUIRED" or \
            sample["artifactBinding"] != "EXTERNAL_INSTALLED_CODE_REQUIRED":
        raise ValueError("observation is not an acceptance record")
    for name in ("foreground", "armed", "committed", "capacityExceeded", "expired"):
        if type(sample[name]) is not bool:
            raise ValueError("observation boolean")
    for name in ("expectedEntities", "renderableEntities", "sceneEntities", "drawnEntities"):
        if type(sample[name]) is not int or not 0 <= sample[name] <= 4096:
            raise ValueError("observation count")
    for name in fields & (FRAME | {"elapsedMs"}):
        value = sample[name]
        if type(value) is not str or re.fullmatch(r"0|[1-9][0-9]{0,19}", value) is None or \
                int(value) > 2**64 - 1:
            raise ValueError("observation integer")
    # Retained bytes are an untrusted local observation. Even plausible positive
    # values do not establish source, installed binary, run, scene or pixel identity.
    return sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        sample = inspect(args.observation)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(sample, stream, sort_keys=True)
            stream.write("\n")
    except (OSError, ValueError, TypeError, UnicodeError):
        print("IOS_WORLD_OBSERVATION_UNAVAILABLE", file=sys.stderr)
        return 1
    print("IOS_WORLD_OBSERVATION_RETAINED_NOT_ACCEPTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
