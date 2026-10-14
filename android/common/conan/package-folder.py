#!/usr/bin/env python3
"""Resolve one exact package directory from prepared CMakeDeps metadata."""
import argparse
from pathlib import Path
import re
import sys


def package_folder(generator, package):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", package):
        raise ValueError("invalid package name")
    generator = Path(generator)
    if generator.is_symlink() or not generator.is_file():
        raise ValueError("missing regular package generator")
    matches = re.findall(r'^set\(' + re.escape(package) +
                         r'_PACKAGE_FOLDER_DEBUG "([^"\n\r]+)"\)$',
                         generator.read_text(encoding="utf-8"), re.MULTILINE)
    if len(matches) != 1 or any(c in matches[0] for c in '$;\\\0'):
        raise ValueError("ambiguous or unsafe package binding")
    folder = Path(matches[0])
    if not folder.is_absolute() or not folder.is_dir() or folder.resolve(strict=True) != folder:
        raise ValueError("package binding is not a canonical existing directory")
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generator")
    parser.add_argument("package")
    args = parser.parse_args()
    try:
        print(package_folder(args.generator, args.package))
    except (OSError, ValueError) as error:
        print("PACKAGE_INPUT_REJECTED: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
