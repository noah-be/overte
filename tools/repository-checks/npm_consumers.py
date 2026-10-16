#!/usr/bin/env python3
"""Finite npm dependency impact selection from complete immutable Git objects.

This module selects and runs bounded consumers; it does not authenticate a
current PR, remote repository, workflow or reusable receipt. Its trusted caller
must establish those identities.
Unknown inputs select the conservative package profile; they never certify a
native build or an unexecuted test. Unrelated CI ownership remains independent.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_TREE_BYTES = 20_000_000
MAX_LOCK_BYTES = 1_000_000
MAX_ENTRIES = 200_000
S3 = "script-archive/marketplace/S3Server"
BROWSER = "browser-client"
# Reviewed package complements contain paths, ordinary modes and Git blob IDs.
# The lock graph complement independently binds all *other* dependencies and root
# keys, including unchanged lifecycle packages. Equal candidate-supplied graphs
# alone cannot authorize an unknown historical graph.
PROJECTS = {
    BROWSER: {
        "profile": "source-map-postcss-v1", "node": "node_modules/source-map-js",
        "complement": "6a2aeca9aeb11a0540bdd7aa6b4a146d4622a43ad85ee6e36e37af38cf7570cd",
        "entries": 1110,
        "graph": "496f28d39f258a7e15d0155804614f743315312930394bc08fe3adbb3d7c0ba3",
        "postcss": True,
        "old": {'version': '1.2.1', 'resolved': 'https://registry.npmjs.org/source-map-js/-/source-map-js-1.2.1.tgz', 'integrity': 'sha512-UXWMKhLOwVKb728IUtQPXxfYU+usdybtUrK/8uGE8CQMvrhOpwvzDBwj0QhSL7MQc7vIsISBG8VQ8+IDQxpfQA==', 'dev': True, 'license': 'BSD-3-Clause', 'engines': {'node': '>=0.10.0'}},
        "new": {'version': '1.2.2', 'resolved': 'https://registry.npmjs.org/source-map-js/-/source-map-js-1.2.2.tgz', 'integrity': 'sha512-KGj/8Y43x35aZVDtt+J4mK1hoLGHULMYfSkODJNQjNDC3oW1PqPoxMwo0pLUsWM/UEGzON/NxeHywEfNXNP3Vw==', 'dev': True, 'license': 'BSD-3-Clause', 'engines': {'node': '>=0.10.0'}},
    },
    S3: {
        "profile": "proxy-addr-express-v1", "node": "node_modules/proxy-addr",
        "complement": "a58cf144734539ed69c01c7ee40c26c5e612fa47b8b0333f82ee8531ee553290",
        "entries": 4,
        "graph": "2ec8fba5ca31b891db0aa05728b1515cc6bca59e111bb9eb7a345bb6a347c899",
        "postcss": False,
        "old": {'version': '2.0.7', 'resolved': 'https://registry.npmjs.org/proxy-addr/-/proxy-addr-2.0.7.tgz', 'integrity': 'sha512-llQsMLSUDUPT44jdrU/O37qlnifitDP+ZwrmmZcoSKyLKvtZxpyV0n2/bD/N4tBAAZ/gJEdZU7KMraoK1+XYAg==', 'license': 'MIT', 'dependencies': {'forwarded': '0.2.0', 'ipaddr.js': '1.9.1'}, 'engines': {'node': '>= 0.10'}},
        "new": {'version': '2.0.8', 'resolved': 'https://registry.npmjs.org/proxy-addr/-/proxy-addr-2.0.8.tgz', 'integrity': 'sha512-5nnx0yGyVUcY6t9RnWcARWtwT9F1D8O9rt08htPvnd49W1IgZtmLkhu9WfMzQj1cFxjHIO6connUNVW5k7AVyQ==', 'license': 'MIT', 'dependencies': {'forwarded': '0.2.0', 'ipaddr.js': '1.9.1'}, 'engines': {'node': '>= 0.10'}, 'funding': {'type': 'opencollective', 'url': 'https://opencollective.com/express'}},
    },
}
PROBES = {BROWSER: "npm-source-map-tests.cjs", S3: "npm-proxy-addr-tests.cjs"}
ROOT = Path(__file__).resolve().parents[2]

# npm workspace/config discovery can occur above a package. PostCSS discovery
# also searches ancestor package/config files, even when the package is intact.
# Package-local entries are already in the reviewed complete package complement.
NPM_CONFIG_NAMES = frozenset({
    "package.json", "package-lock.json", "npm-shrinkwrap.json", ".npmrc",
    ".yarnrc", ".yarnrc.yml", ".pnpmfile.cjs", "pnpm-workspace.yaml",
    ".nvmrc", ".node-version", ".tool-versions",
})
MODES = {"100644": "blob", "100755": "blob", "120000": "blob", "160000": "commit"}


class ConsumerError(ValueError):
    """A bounded, complete source inventory could not be established."""


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


# All reviewed ancestor discovery entries are absent, including root package.json.
# Hashing the fixed empty inventory is not a candidate-supplied reader anchor.
REVIEWED_DISCOVERY = {project: _digest([]) for project in PROJECTS}


def _git(repository, *arguments, limit=MAX_TREE_BYTES):
    try:
        result = subprocess.run(["git", "--no-replace-objects", "--no-optional-locks",
                                 "-c", "gc.auto=0", "-c", "maintenance.auto=false", *arguments],
                                cwd=repository, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise ConsumerError("immutable-source-unavailable") from error
    if result.returncode or len(result.stdout) > limit or len(result.stderr) > 65_536:
        raise ConsumerError("immutable-source-unavailable-or-oversized")
    return result.stdout


def _snapshot(repository, revision):
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        raise ConsumerError("exact-commit-required")
    resolved = _git(repository, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}", limit=100).decode().strip()
    if resolved != revision:
        raise ConsumerError("exact-commit-required")
    tree = _git(repository, "rev-parse", revision + "^{tree}", limit=100).decode().strip()
    if not SHA.fullmatch(tree):
        raise ConsumerError("invalid-root-tree")
    raw = _git(repository, "ls-tree", "-rz", "--full-tree", tree)
    if not raw or not raw.endswith(b"\0"):
        raise ConsumerError("empty-or-incomplete-tree")
    records = raw.split(b"\0")[:-1]
    if len(records) > MAX_ENTRIES:
        raise ConsumerError("source-entry-bound-exceeded")
    entries = {}
    for record in records:
        metadata, encoded = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        name = encoded.decode("utf-8", errors="strict")
        path = PurePosixPath(name)
        if not name or "\\" in name or path.is_absolute() or str(path) != name \
                or any(part in {".", ".."} or part.casefold() == ".git" for part in path.parts) \
                or name in entries or MODES.get(mode) != kind or not SHA.fullmatch(oid):
            raise ConsumerError("invalid-source-entry")
        entries[name] = {"path": name, "mode": mode, "type": kind, "oid": oid}
    return {"revision": revision, "tree": tree, "entries": entries}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConsumerError("duplicate-lockfile-field")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ConsumerError("nonfinite-lockfile-number")


def _lock(repository, snapshot, project):
    entry = snapshot["entries"].get(project + "/package-lock.json")
    if entry is None or entry["mode"] != "100644" or entry["type"] != "blob":
        raise ConsumerError("missing-or-nonordinary-lockfile")
    size = _git(repository, "cat-file", "-s", entry["oid"], limit=30).decode().strip()
    if not size.isdigit() or not 0 < int(size) <= MAX_LOCK_BYTES:
        raise ConsumerError("lockfile-size-bound-exceeded")
    raw = _git(repository, "cat-file", "blob", entry["oid"], limit=MAX_LOCK_BYTES)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_invalid_constant)
    if not isinstance(value, dict) or type(value.get("lockfileVersion")) is not int \
            or value["lockfileVersion"] != 3 or not isinstance(value.get("packages"), dict) \
            or any(not isinstance(item, dict) for item in value["packages"].values()):
        raise ConsumerError("unsupported-lockfile-structure")
    return value


def _complement(snapshot, project):
    lock = project + "/package-lock.json"
    return [item for name, item in sorted(snapshot["entries"].items())
            if name.startswith(project + "/") and name != lock]


def _discovery(snapshot, project, postcss):
    ancestors = set()
    parent = PurePosixPath(project).parent
    while True:
        ancestors.add("" if str(parent) == "." else str(parent))
        if str(parent) == ".":
            break
        parent = parent.parent
    selected = []
    for name, item in sorted(snapshot["entries"].items()):
        path = PurePosixPath(name)
        parent = "" if str(path.parent) == "." else str(path.parent)
        npm = parent in ancestors and path.name in NPM_CONFIG_NAMES
        css = postcss and (parent in ancestors and (
            path.name == ".config" or path.name.startswith(".postcss") or path.name.startswith("postcss.config.")) or any(
                name.startswith((ancestor + "/" if ancestor else "") + ".config/")
                and ("postcss" in path.name or "/postcss/" in name) for ancestor in ancestors))
        if npm or css:
            selected.append(item)
    return selected


def _graph(lock, node):
    return {**lock, "packages": {name: item for name, item in lock["packages"].items() if name != node}}


def _result(profile, required, reason, *, changed_nodes=(), boundary=None, changed_paths=()):
    return {"profile": profile, "required": required, "reason": reason,
            "changed_nodes": list(changed_nodes), "changed_paths": list(changed_paths),
            "boundary": boundary or {}, "execution": "not-performed"}


def _project(repository, previous, current, project, policy):
    old, new = previous["entries"], current["entries"]
    changed = [name for name in sorted(old.keys() | new.keys()) if old.get(name) != new.get(name)
               and (name == project or name.startswith(project + "/"))]
    before_discovery = _digest(_discovery(previous, project, policy["postcss"]))
    after_discovery = _digest(_discovery(current, project, policy["postcss"]))
    boundary = {"project_complement": {"expected": policy["complement"],
        "base": _digest(_complement(previous, project)), "candidate": _digest(_complement(current, project))},
        "discovery": {"expected": REVIEWED_DISCOVERY[project],
            "base": before_discovery, "candidate": after_discovery}}
    def full(reason, nodes=()):
        return _result("full", True, reason, changed_nodes=nodes, boundary=boundary, changed_paths=changed)
    if not changed and before_discovery == after_discovery:
        return _result("none", False, "unchanged-package-inputs", boundary=boundary)
    if before_discovery != REVIEWED_DISCOVERY[project] or after_discovery != REVIEWED_DISCOVERY[project]:
        return full("ancestor-config-discovery-not-reviewed")
    if project + "/package.json" not in old or project + "/package.json" not in new:
        return full("package-manifest-unavailable")
    if changed != [project + "/package-lock.json"]:
        return full("package-consumers-or-scripts-changed")
    if any(boundary["project_complement"][side] != policy["complement"] for side in ("base", "candidate")) \
            or any(len(_complement(snapshot, project)) != policy["entries"] for snapshot in (previous, current)):
        return full("package-reader-complement-not-reviewed")
    try:
        before, after = (_lock(repository, snapshot, project) for snapshot in (previous, current))
        nodes = [name for name in sorted(before["packages"].keys() | after["packages"].keys())
                 if _canonical(before["packages"].get(name)) != _canonical(after["packages"].get(name))]
        boundary["lock_graph_complement"] = {"expected": policy["graph"],
            "base": _digest(_graph(before, policy["node"])), "candidate": _digest(_graph(after, policy["node"]))}
        if any(boundary["lock_graph_complement"][side] != policy["graph"] for side in ("base", "candidate")):
            return full("historical-lock-graph-not-reviewed", nodes)
        if _canonical(before) == _canonical(after):
            if _canonical(before["packages"].get(policy["node"])) not in (
                    _canonical(policy["old"]), _canonical(policy["new"])):
                return full("unchanged-dependency-version-not-reviewed")
            return _result("none", False, "reviewed-lockfile-format-only", boundary=boundary, changed_paths=changed)
        if nodes != [policy["node"]] or _canonical(before["packages"].get(policy["node"])) != _canonical(policy["old"]) \
                or _canonical(after["packages"].get(policy["node"])) != _canonical(policy["new"]):
            return full("unsupported-lockfile-node-change", nodes)
        selected = _result(policy["profile"], True, "reviewed-single-dependency-security-update",
                           changed_nodes=nodes, boundary=boundary, changed_paths=changed)
        selected["dependency"] = {"node": policy["node"], "base": policy["old"], "candidate": policy["new"]}
        selected["constraints"] = {"node_major": 22, "node_minimum": "22.12.0", "npm_major": 10,
            "npm_install": ["npm", "ci", "--ignore-scripts", "--no-fund", "--no-audit"],
            "ambient_node_options_and_node_path": "must-be-empty",
            "external_npm_user_and_global_configuration": "must-be-disabled-by-trusted-runner",
            "lifecycle": "no install/prebuild/build hooks selected; focused installed dependencies are pure JavaScript",
            "browser_unchanged_install_hooks": "esbuild and Darwin fsevents are unchanged and not used by this profile"
                if project == BROWSER else "no install-script packages in the reviewed S3 graph"}
        return selected
    except (ConsumerError, ValueError, UnicodeError, RecursionError):
        return full("lockfile-metadata-unavailable-or-invalid")


def select(repository, base, candidate):
    """Return independent per-project profiles, never a whole-PR host mode.

    SHA arguments must identify commits directly. Formatting-only reviewed lock
    changes select no package execution. Unknown/empty metadata is conservative;
    a verified unchanged immutable package is represented as ``none``, not PASS.
    """
    result = {"schema": 1, "base": {"revision": base if isinstance(base, str) and SHA.fullmatch(base) else None, "tree": None},
              "candidate": {"revision": candidate if isinstance(candidate, str) and SHA.fullmatch(candidate) else None, "tree": None},
              "unknown": False, "projects": {}}
    try:
        previous, current = (_snapshot(Path(repository), revision) for revision in (base, candidate))
        for key, snapshot in (("base", previous), ("candidate", current)):
            result[key] = {name: snapshot[name] for name in ("revision", "tree")}
        result["projects"] = {project: _project(repository, previous, current, project, policy)
                              for project, policy in PROJECTS.items()}
    except (ConsumerError, ValueError, UnicodeError, RecursionError, OSError):
        result["unknown"] = True
        result["projects"] = {project: _result("full", True, "immutable-input-inventory-unavailable")
                              for project in PROJECTS}
    result["plan"] = _digest(result)
    return result


def run(repository, selection, projects):
    """Execute supported consumers once; a caller must authenticate the event.

    This does not accept a candidate-selected command, profile or source digest.
    Complete immutable selection is independently recomputed before execution.
    Package installation is script-free; no browser, Vite or native build runs.
    """
    repository = Path(repository).resolve(strict=True)
    if not isinstance(projects, list) or not projects or len(set(projects)) != len(projects) \
            or any(project not in PROJECTS for project in projects):
        raise ConsumerError("unsupported-or-duplicate-consumer-projects")
    if not isinstance(selection, dict):
        raise ConsumerError("consumer-selection-required")
    try:
        base = selection['base']['revision']
        candidate = selection['candidate']['revision']
    except (KeyError, TypeError) as error:
        raise ConsumerError("consumer-selection-identity-missing") from error
    expected = select(repository, base, candidate)
    if selection != expected or expected['unknown']:
        raise ConsumerError("consumer-selection-does-not-match-immutable-inputs")
    for project in projects:
        selected = expected['projects'][project]
        if selected['profile'] != PROJECTS[project]['profile'] or not selected['required']:
            raise ConsumerError("focused-consumer-profile-not-selected")
        # A sparse immutable inventory is permitted, but npm consumes the actual
        # package bytes. Reject missing, extra, aliased or edited materialization.
        folder = repository / project
        if (folder / 'node_modules').is_symlink():
            raise ConsumerError("consumer-node-modules-cannot-be-a-symbolic-link")
        for path in (folder, *folder.parents):
            if path == repository:
                break
            if path.is_symlink() or not path.is_dir():
                raise ConsumerError("consumer-directory-is-not-ordinary")
        for name in ('package.json', 'package-lock.json'):
            path = folder / name
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o111:
                raise ConsumerError("consumer-manifests-are-not-ordinary")
        # Git status omits ignored files. They must not inject local npm or
        # ancestor workspace/config discovery into a reviewed immutable graph.
        for name in ('.npmrc', 'npm-shrinkwrap.json'):
            path = folder / name
            if path.exists() or path.is_symlink():
                raise ConsumerError("unreviewed-materialized-package-config")
        ancestor = folder.parent
        while True:
            names = set(NPM_CONFIG_NAMES)
            if project == BROWSER:
                names.add('.config')
                names.update(path.name for path in ancestor.iterdir()
                             if path.name.startswith(('.postcss', 'postcss.config.')))
            if any((ancestor / name).exists() or (ancestor / name).is_symlink() for name in names):
                raise ConsumerError("unreviewed-materialized-ancestor-config")
            if ancestor == repository:
                break
            ancestor = ancestor.parent
    if _git(repository, 'rev-parse', 'HEAD', limit=100).decode().strip() != candidate \
            or _git(repository, 'status', '--porcelain', '--untracked-files=all'):
        raise ConsumerError("consumer-checkout-must-match-clean-candidate")

    # Start from an allowlist: no npm configuration, NODE_OPTIONS/NODE_PATH,
    # credentials, GitHub command files or runner tokens reach package children.
    environment = {name: os.environ[name] for name in (
        'HOME', 'TMPDIR', 'TMP', 'TEMP', 'LANG', 'LC_ALL', 'SYSTEMROOT') if name in os.environ}
    paths = []
    for directory in os.environ.get('PATH', os.defpath).split(os.pathsep):
        path = Path(directory)
        if path.is_absolute() and not path.resolve().is_relative_to(repository):
            paths.append(directory)
    environment.update(PATH=os.pathsep.join(paths), CI='true', NODE_OPTIONS='', NODE_PATH='')
    node = shutil.which('node', path=environment['PATH'])
    npm = shutil.which('npm', path=environment['PATH'])
    if node is None or npm is None:
        raise ConsumerError("node-and-npm-are-required")

    def command(arguments, cwd, *, capture=False):
        return subprocess.run(arguments, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                              check=True, timeout=240, text=True,
                              stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.PIPE if capture else None)

    with tempfile.TemporaryDirectory(prefix='overte-npm-consumer-config-') as directory:
        configuration = Path(directory)
        for name in ('user', 'global'):
            path = configuration / name
            path.write_text('')
            environment['NPM_CONFIG_' + name.upper() + 'CONFIG'] = str(path)
        version = command([node, '--version'], ROOT, capture=True).stdout.strip()
        npm_version = command([npm, '--version'], ROOT, capture=True).stdout.strip()
        match = re.fullmatch(r'v22\.([0-9]+)\.([0-9]+)', version)
        if not match or int(match[1]) < 12 or not re.fullmatch(r'10\.[0-9]+\.[0-9]+', npm_version):
            raise ConsumerError("focused-consumers-require-reviewed-node22-and-npm10")
        for project in projects:
            folder = repository / project
            probe = ROOT / 'tools/repository-checks' / PROBES[project]
            if probe.is_symlink() or not probe.is_file():
                raise ConsumerError("trusted-consumer-probe-is-unavailable")
            # npm10 otherwise discovers workspaces/config above the checkout.
            # A CLI prefix stops that search before reading an outer .npmrc.
            prefix = ['--prefix', str(folder), '--workspaces=false']
            command([npm, 'ci', '--ignore-scripts', '--no-fund', '--no-audit', *prefix], folder)
            command([npm, 'audit', '--audit-level=low', *prefix], folder)
            command([node, str(probe), str(folder)], folder)
            if project == S3:
                # Preserve existing application assertions without installing
                # the package again or turning a proxy fix into an app build.
                command([npm, 'test', '--ignore-scripts', *prefix], folder)
    if _git(repository, 'rev-parse', 'HEAD', limit=100).decode().strip() != candidate \
            or _git(repository, 'status', '--porcelain', '--untracked-files=all'):
        raise ConsumerError("consumer-checkout-changed-during-execution")
    return {'candidate': candidate, 'plan': expected['plan'], 'projects': projects,
            'node': version, 'npm': npm_version, 'verified': True, 'application_builds': 0}
