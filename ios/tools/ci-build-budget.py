#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
"""Export one Apple CI compiler budget for CMake, Conan and Autoninja."""

import argparse
import multiprocessing
from pathlib import Path


def positive_integer(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise argparse.ArgumentTypeError("jobs must be a positive integer")
    return int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=positive_integer, default=2)
    parser.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args()
    # The pinned Autoninja computes local jobs as cpu_count + CORE_ADDITION.
    # CORE_LIMIT independently caps its remote-execution branch. Do not use
    # CORE_MULTIPLIER: it does not control local Ninja in that revision.
    values = {
        "OVERTE_IOS_BUILD_JOBS": args.jobs,
        "CMAKE_BUILD_PARALLEL_LEVEL": args.jobs,
        "NINJA_CORE_ADDITION": args.jobs - multiprocessing.cpu_count(),
        "NINJA_CORE_LIMIT": args.jobs,
    }
    with args.github_env.open("a", encoding="utf-8") as stream:
        for name, value in values.items():
            stream.write(f"{name}={value}\n")
    print(f"Apple CI compiler budget: {args.jobs} jobs")


if __name__ == "__main__":
    main()
