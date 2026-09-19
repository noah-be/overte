"""Conservative pre-build scope plus a Release CMake File API dependency closure."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import platform
from common import ROOT, git, json_read, digest

PREFIXES = ("ios/", "interface/", "libraries/", "cmake/", "scripts/", "plugins/opusCodec/",
            "plugins/pcmCodec/", "tests/device/", "provenance/", "LICENSES/")
FILES = {"CMakeLists.txt", "conanfile.py", "LICENSE", ".gitignore", ".gitmodules"}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".m", ".mm", ".swift",
                   ".metal", ".qml", ".js", ".py", ".sh", ".cmake", ".json", ".env",
                   ".in", ".plist", ".xcprivacy", ".entitlements", ".xml", ".txt", ".md",
                   ".yml", ".yaml", ".qrc", ".pro", ".pri", ".frag", ".vert", ".slh"}


def swift_scope(paths):
    """Apple-host helper parsing is deferred on Linux; product Swift is mandatory."""
    selected, deferred = [], []
    for path in paths:
        if not path.endswith(".swift"):
            continue
        host_tool = path.startswith(("ios/ci/", "ios/tools/", "ios/tests/", "tests/"))
        (deferred if host_tool and platform.system() != "Darwin" else selected).append(path)
    return selected, deferred


def relevant(name):
    return (name in FILES or name.startswith(PREFIXES)
            or name.startswith(".github/workflows/ios-")
            or name.startswith("macos/conan/"))


class Scope:
    def __init__(self, ctx):
        self.tracked = git("ls-files", "-z").split("\0")[:-1]
        self.paths = [p for p in self.tracked if relevant(p)]
        # New gate files must also be inspected before they have been committed.
        self.paths = sorted(set(self.paths) | {p for p in git("ls-files", "--others", "--exclude-standard", "-z").split("\0") if p and relevant(p)})
        self.texts = {}
        self.hashes = {}
        for name in self.paths:
            path = ROOT / name
            if path.is_symlink() or not path.is_file():
                continue
            self.hashes[name] = digest(path)
            if (path.suffix in SOURCE_SUFFIXES or path.name in {"CMakeLists.txt", "LICENSE", ".gitignore"}) and path.stat().st_size <= 8 * 1024 * 1024:
                try:
                    self.texts[name] = path.read_text(encoding="utf-8")
                except UnicodeError:
                    pass
        ctx.inventories["scope"] = {"mode": "conservative", "paths": self.paths,
            "sha256": self.hashes, "note": "May include platform-conditional shared code; not proof of linked reachability."}

    def production_texts(self):
        return {p: text for p, text in self.texts.items()
                if not p.startswith(("ios/tests/", "ios/release-check/", "tests/", "ios/ci/", "ios/tools/"))
                and Path(p).suffix not in {".md", ".yml", ".yaml"}}


def file_api_scope(ctx, build: Path, source: Path):
    reply = build / ".cmake/api/v1/reply"
    indexes = sorted(reply.glob("index-*.json"))
    if not ctx.need(indexes, "build-codemodel", "Release CMake File API reply is required."):
        return
    index = json_read(indexes[-1])
    model_file = index["reply"]["codemodel-v2"]["jsonFile"]
    model = json_read(reply / model_file)
    configs = [x for x in model["configurations"] if x["name"] == "Release"]
    if not ctx.need(len(configs) == 1, "build-release-model", "Exactly one Release codemodel is required."):
        return
    targets = {x["id"]: x for x in configs[0]["targets"]}
    pending = [x["id"] for x in targets.values() if x["name"] == "Overte"]
    if not ctx.need(len(pending) == 1, "build-product-target", "The Overte Full Client target must exist."):
        return
    seen, sources, externals, fragments = set(), set(), set(), []
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        target = json_read(reply / targets[key]["jsonFile"])
        pending += [x["id"] for x in target.get("dependencies", []) if x["id"] in targets]
        for item in target.get("sources", []):
            p = Path(item["path"])
            p = (source / p).resolve() if not p.is_absolute() else p.resolve()
            if p.is_relative_to(source):
                sources.add(str(p.relative_to(source)))
            elif not p.is_relative_to(build):
                externals.add(str(p))
        fragments += target.get("link", {}).get("commandFragments", [])
    ctx.inventories["linked-scope"] = {"sourceRevision": ctx.revision, "configuration": "Release",
        "target": "Overte", "targets": sorted(targets[k]["name"] for k in seen),
        "sources": sorted(sources), "externalSources": sorted(externals), "linkFragments": fragments,
        "bundledResourceRoots": ["interface/resources", "scripts", "ios/resources"]}
    ctx.need(bool(sources), "build-empty-scope", "The linked source closure must be nonempty.")
    if externals:
        ctx.review("external-source-provenance", "Review generated/external source provenance against the clean-build inputs.")
