#!/usr/bin/env python3
"""Reject shared includes of Android-owned headers outside Android-only guards.

This is a conservative ownership check, not a C++ compiler. Unknown conditions
may be true or false. Only documented Android selectors can exclude a branch
from non-Android builds; unsupported expressions never prove exclusion.
"""

from pathlib import Path, PurePosixPath
import argparse
import json
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
ANDROID_MACROS = {"Q_OS_ANDROID", "__ANDROID__", "ANDROID_APP_PHONE_INTERFACE",
                  "OVERTE_PICO_SETUP"}
UNKNOWN = frozenset((False, True))


def negate(value):
    return frozenset(not item for item in value)


def combine(left, right, operation):
    return frozenset(operation(a, b) for a in left for b in right)


def condition(expression):
    """Possible values in a non-Android compilation (never execute source)."""
    expression = re.sub(r"defined\s*\(\s*(\w+)\s*\)", r"\1", expression)
    expression = re.sub(r"defined\s+(\w+)", r"\1", expression)
    tokens = re.findall(r"\w+|&&|\|\||[!()]|\S", expression)
    position = 0

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("incomplete condition")
        token = tokens[position]
        position += 1
        if token == "!":
            return negate(atom())
        if token == "(":
            value = either()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("unclosed condition")
            position += 1
            return value
        if token in ANDROID_MACROS or token == "0":
            return frozenset((False,))
        if token == "1":
            return frozenset((True,))
        if re.fullmatch(r"[A-Za-z_]\w*", token):
            return UNKNOWN
        raise ValueError("unsupported condition")

    def both():
        nonlocal position
        value = atom()
        while position < len(tokens) and tokens[position] == "&&":
            position += 1
            value = combine(value, atom(), lambda a, b: a and b)
        return value

    def either():
        nonlocal position
        value = both()
        while position < len(tokens) and tokens[position] == "||":
            position += 1
            value = combine(value, both(), lambda a, b: a or b)
        return value

    try:
        value = either()
        return value if position == len(tokens) else UNKNOWN
    except ValueError:
        return UNKNOWN


def violations(source, header_names, roots):
    source = re.sub(r"\\\r?\n", " ", source)
    source = re.sub(r"/\*.*?\*/", lambda m: " " + "\n" * m[0].count("\n"), source, flags=re.S)
    active, stack, findings = frozenset((True,)), [], []
    for line_number, line in enumerate(source.splitlines(), 1):
        match = re.match(r"\s*#\s*(\w+)\b(.*)", line.split("//", 1)[0])
        if not match:
            continue
        directive, value = match[1], match[2].strip()
        if directive in {"if", "ifdef", "ifndef"}:
            branch = condition(value)
            if directive == "ifndef":
                branch = negate(branch)
            stack.append((active, negate(branch)))
            active = combine(active, branch, lambda a, b: a and b)
        elif directive in {"elif", "else"}:
            if not stack:
                raise ValueError("unmatched conditional branch")
            parent, remaining = stack[-1]
            branch = condition(value) if directive == "elif" else frozenset((True,))
            active = combine(parent, combine(remaining, branch, lambda a, b: a and b),
                             lambda a, b: a and b)
            stack[-1] = (parent, combine(remaining, negate(branch), lambda a, b: a and b))
        elif directive == "endif":
            if not stack:
                raise ValueError("unmatched endif")
            active, _ = stack.pop()
        elif directive == "include" and True in active:
            include = re.fullmatch(r'[<"]([^>"]+)[>"]', value)
            if not include:
                continue
            path = PurePosixPath(include[1])
            components = [part for part in path.parts if part != ".."]
            owned = path.name in header_names or any(
                tuple(components[i:i + len(root)]) == root
                for root in roots for i in range(len(components)))
            if owned:
                findings.append(f"{line_number}: Android-only include {include[1]} can reach a non-Android build")
    if stack:
        raise ValueError("unclosed preprocessor conditional")
    return findings


def audit(root=ROOT):
    policy = json.loads((root / ".github/platform-source-policy.json").read_text())
    owned_files = set(policy["android_files"])
    owned_roots = policy["android_roots"]
    headers = {PurePosixPath(path).name for path in owned_files
               if PurePosixPath(path).suffix in {".h", ".hpp"}}
    roots = [PurePosixPath(path).parts for path in owned_roots]
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    findings = []
    for name in files:
        path = root / name
        if (PurePosixPath(name).suffix not in {".h", ".hpp", ".c", ".cpp", ".cc", ".cxx", ".mm"}
                or name in owned_files or any(name.startswith(prefix + "/") for prefix in owned_roots)
                or not path.is_file()):
            continue
        for finding in violations(path.read_text(errors="replace"), headers, roots):
            findings.append(f"{name}:{finding}")
    return findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings = audit(args.root)
    print("\n".join(findings) if findings else "Shared Android include boundary: PASS")
    raise SystemExit(bool(findings))
