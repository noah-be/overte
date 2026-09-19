#!/usr/bin/env python3
"""Resolve pinned dependency bundles and audit all live fork branches/releases.

Read-only by design. Publication and retirement remain explicit operations;
`audit --allow-retiring` is the prerequisite for retiring old release assets.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/dependency-releases.json"
REPOSITORY = "noah-be/overte"
FAMILIES = {"phone": "android-phone-16k-deps-v", "pico": "pico4-deps-v"}
ASSETS = {
    "phone": {"android-phone-16k-conan.tgz"},
    "pico": {"pico4-node-conan.tgz", "pico4-qt-conan.tgz", "pico4-runtime.tgz"},
}
TAG_PATTERN = r"(android-phone-16k-deps-v|pico4-deps-v)[0-9]+"
CONSUMERS = {
    "android/phone/phone-prebuilt-16k-deps.sh": "phone",
    "android/vr/pico/build.sh": "pico",
    ".github/workflows/pico4-release-candidate.yml": "pico",
}


class PolicyError(ValueError):
    pass


def run(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.PIPE)


def load(text: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PolicyError(f"Duplicate policy key: {key}")
            result[key] = value
        return result

    data = json.loads(text, object_pairs_hook=unique)
    if set(data) != {"schema", "repository", "bundles"}:
        raise PolicyError("Unexpected policy fields")
    if data["schema"] != 1 or data["repository"] != REPOSITORY:
        raise PolicyError("Unsupported schema or repository")
    if set(data["bundles"]) != set(FAMILIES):
        raise PolicyError("Exactly one Phone and one Pico bundle are required")
    for family, item in data["bundles"].items():
        if set(item) != {"tag", "tag_object", "assets"}:
            raise PolicyError(f"Unexpected bundle fields: {family}")
        if not re.fullmatch(FAMILIES[family] + r"[1-9][0-9]*", item["tag"]):
            raise PolicyError(f"Invalid immutable tag: {family}")
        if not re.fullmatch(r"[0-9a-f]{40}", item["tag_object"]):
            raise PolicyError(f"Invalid tag object: {family}")
        if set(item["assets"]) != ASSETS[family]:
            raise PolicyError(f"Unexpected or missing archive: {family}")
        if not all(re.fullmatch(r"[0-9a-f]{64}", v) for v in item["assets"].values()):
            raise PolicyError(f"Invalid archive checksum: {family}")
    return data


def checksums(bundle: dict) -> str:
    return "".join(f"{digest}  {name}\n" for name, digest in sorted(bundle["assets"].items()))


def relevant(path: str) -> bool:
    # Historical prose and test fixtures may name retired releases. Executable
    # build/workflow/configuration sources must resolve the central policy.
    parts = Path(path).parts
    return (path != POLICY and "tests" not in parts and "test" not in parts
            and Path(path).suffix in {".sh", ".py", ".json", ".yml", ".yaml",
                                      ".gradle", ".cmake", ".toml", ".env"})


def check_sources(read, matches: list[str]) -> None:
    try:
        profile_text = read("tests/platform-profile.json")
    except (FileNotFoundError, subprocess.CalledProcessError):
        profile_text = None  # Branches predating source ownership keep all consumers.
    try:
        profile = json.loads(profile_text) if profile_text is not None else {"platform": "android"}
        platform = profile["platform"]
        if platform not in ("shared", "android"):
            raise ValueError("Unknown platform")
    except (ValueError, KeyError, TypeError) as error:
        raise PolicyError("Invalid source ownership profile") from error
    for path, family in CONSUMERS.items():
        if platform == "shared" and path.startswith("android/"):
            try:
                read(path)
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
            raise PolicyError(f"Android consumer unexpectedly present on shared profile: {path}")
        source = read(path)
        if platform == "shared" and path.endswith("pico4-release-candidate.yml"):
            if "select-platform-ref:" not in source or "exit 1" not in source or "uses:" in source:
                raise PolicyError("Shared workflow must remain a registration-only stub")
            continue
        if "tools/dependency-releases/check.py" not in source:
            raise PolicyError(f"{path} does not use the central resolver")
        if f"get {family} " not in source and f"checksums {family}" not in source:
            raise PolicyError(f"{path} does not select its dependency bundle")
    bad = []
    for path in sorted(set(matches)):
        if not relevant(path):
            continue
        if path == ".github/sync-test-reuse.json":
            # Exact old blob identities authorize deletion, never a download.
            config = json.loads(read(path))
            config.pop("retired_parent_paths", None)
            if not re.search(TAG_PATTERN, json.dumps(config)):
                continue
        bad.append(path)
    if bad:
        raise PolicyError("Hardcoded dependency tags outside policy: " + ", ".join(bad))


def check_checksum_paths(paths: list[str]) -> None:
    if any(p.startswith("android/common/conan/prebuilt/") and p.endswith(".sha256") for p in paths):
        raise PolicyError("Duplicated dependency checksum files; use the central resolver")


def local_check(root: Path, canonical_ref: str | None = None) -> dict:
    data = load((root / POLICY).read_text())
    paths = run("git", "ls-files", "--cached", "--others", "--exclude-standard", cwd=root).splitlines()
    check_checksum_paths([p for p in paths if (root / p).exists()])
    matches = [p for p in paths if relevant(p) and (root / p).is_file()
               and re.search(TAG_PATTERN, (root / p).read_text(errors="replace"))]
    check_sources(lambda p: (root / p).read_text(), matches)
    if canonical_ref:
        canonical = load(run("git", "show", f"{canonical_ref}:{POLICY}", cwd=root))
        if data != canonical:
            raise PolicyError("Dependency policy differs from current main; synchronize the parent first")
    return data


def api(endpoint: str):
    return json.loads(run("gh", "api", endpoint))


def pages(endpoint: str) -> list:
    result = []
    for page in range(1, 100):
        batch = api(f"{endpoint}?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise PolicyError("Expected a paginated GitHub list")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise PolicyError("Pagination limit reached")


def remote_heads() -> dict:
    return {line.split("\t")[1].removeprefix("refs/heads/"): line.split("\t")[0]
            for line in run("git", "ls-remote", "--heads", f"https://github.com/{REPOSITORY}.git").splitlines()}


def inventory(data: dict, releases: list, tags: dict, allow_retiring: bool) -> list[str]:
    current = {b["tag"]: b for b in data["bundles"].values()}
    dependency_releases = [r for r in releases if re.fullmatch(TAG_PATTERN, r["tag_name"])]
    seen = {}
    for release in dependency_releases:
        tag = release["tag_name"]
        if tag in seen:
            raise PolicyError(f"Duplicate release for {tag}")
        seen[tag] = release
        if tag not in current:
            continue
        bundle = current[tag]
        if release["draft"] or release["prerelease"]:
            raise PolicyError(f"Dependency bundle is not published: {tag}")
        assets = {a["name"]: a for a in release["assets"]}
        if len(assets) != len(release["assets"]):
            raise PolicyError(f"Duplicate assets: {tag}")
        allowed = set(bundle["assets"]) | {tag + ".sha256"}
        if not set(bundle["assets"]) <= set(assets) or set(assets) - allowed:
            raise PolicyError(f"Unexpected or missing release assets: {tag}")
        for name, digest in bundle["assets"].items():
            if assets[name].get("digest") != "sha256:" + digest:
                raise PolicyError(f"GitHub asset digest mismatch: {tag}/{name}")
        if tags.get(tag) != bundle["tag_object"]:
            raise PolicyError(f"Tag object changed or missing: {tag}")
    if set(current) - set(seen):
        raise PolicyError("Current dependency release is missing")
    extras = sorted((set(seen) | {t for t in tags if re.fullmatch(TAG_PATTERN, t)}) - set(current))
    if extras and not allow_retiring:
        raise PolicyError("Retired dependency releases/tags still present: " + ", ".join(extras))
    return extras


def audit(root: Path, allow_retiring: bool = False) -> dict:
    if api(f"repos/{REPOSITORY}")["full_name"] != REPOSITORY:
        raise PolicyError("Repository ownership mismatch")
    heads = remote_heads()
    # Separate audit refs avoid touching local branches, worktrees, and tags.
    run("git", "fetch", "--no-tags", "--prune", f"https://github.com/{REPOSITORY}.git",
        "+refs/heads/*:refs/dependency-audit/heads/*", cwd=root)
    data = load(run("git", "show", f"{heads['main']}:{POLICY}", cwd=root))
    errors = []
    for branch, sha in sorted(heads.items()):
        try:
            if load(run("git", "show", f"{sha}:{POLICY}", cwd=root)) != data:
                raise PolicyError("policy differs from main")
            paths = run("git", "ls-tree", "-r", "--name-only", sha, "android/common/conan/prebuilt", cwd=root).splitlines()
            check_checksum_paths(paths)
            trusted_paths = ("tools/dependency-releases", ".github/workflows/dependency-releases.yml")
            if run("git", "ls-tree", "-r", sha, *trusted_paths, cwd=root) != run(
                    "git", "ls-tree", "-r", heads["main"], *trusted_paths, cwd=root):
                raise PolicyError("dependency policy tooling differs from main")
            process = subprocess.run(["git", "grep", "-l", "-I", "-E", TAG_PATTERN, sha, "--"],
                                     cwd=root, text=True, capture_output=True)
            if process.returncode not in (0, 1):
                raise PolicyError("source scan failed")
            matches = [p.removeprefix(sha + ":") for p in process.stdout.splitlines()]
            check_sources(lambda p: run("git", "show", f"{sha}:{p}", cwd=root), matches)
        except (ValueError, subprocess.CalledProcessError) as error:
            errors.append(f"{branch}: {str(error)[:200]}")
    if errors:
        raise PolicyError("Active branch drift:\n" + "\n".join(errors))
    releases = pages(f"repos/{REPOSITORY}/releases")
    tags = {r["ref"].removeprefix("refs/tags/"): r["object"]["sha"]
            for r in pages(f"repos/{REPOSITORY}/git/matching-refs/tags/")}
    extras = inventory(data, releases, tags, allow_retiring)
    if remote_heads() != heads:
        raise PolicyError("Remote branches moved during audit; retry")
    return {"repository": REPOSITORY, "heads": heads, "policy": data,
            "retirement_candidates": {t: tags.get(t) for t in extras},
            "current_release_ids": [r["id"] for r in releases
                                    if r["tag_name"] in {b["tag"] for b in data["bundles"].values()}]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    get = sub.add_parser("get")
    get.add_argument("family", choices=FAMILIES)
    get.add_argument("field", choices=("tag", "base-url"))
    sums = sub.add_parser("checksums")
    sums.add_argument("family", choices=FAMILIES)
    check = sub.add_parser("check")
    check.add_argument("--canonical-ref")
    live = sub.add_parser("audit")
    live.add_argument("--allow-retiring", action="store_true",
                      help="Report retirement candidates after checking EVERY live branch")
    args = parser.parse_args()
    try:
        if args.command == "audit":
            print(json.dumps(audit(args.root, args.allow_retiring), indent=2))
        elif args.command == "check":
            local_check(args.root, args.canonical_ref)
            print("Dependency policy and consumers verified")
        else:
            data = load((args.root / POLICY).read_text())
            bundle = data["bundles"][args.family]
            if args.command == "checksums":
                print(checksums(bundle), end="")
            elif args.field == "tag":
                print(bundle["tag"])
            else:
                print(f"https://github.com/{REPOSITORY}/releases/download/{bundle['tag']}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Dependency policy failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
