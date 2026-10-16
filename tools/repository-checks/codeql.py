#!/usr/bin/env python3
"""Plan language-level CodeQL scans from two complete immutable Git trees.

The CodeQL workflow runs this helper from a trusted default-branch checkout,
never a copy from the candidate.
It selects whole-language analyses; it does not restrict files within a scan.

The reviewed no-build configuration has no custom query/model packs or generated
sources. Configuration and action upgrades require review of this policy, too.
Current primary extractor references (reviewed 2026-10-15):
https://github.com/github/codeql/blob/main/javascript/extractor/src/com/semmle/js/extractor/FileExtractor.java
https://github.com/github/codeql/blob/main/python/extractor/semmle/traverser.py
https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("trusted_codeql_input_inventory", ROOT / "tools/test-evidence/inputs.py")
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("trusted immutable input inventory is unavailable")
inputs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(inputs)

LANGUAGES = ("javascript-typescript", "python")
# Exact reviewed controls from c9c17903; do not replace these with candidate
# bytes or hashes computed from an unchecked local working copy.
_REVIEWED_CONTROLS = {
    ".github/codeql/codeql-config.yml": "143b03ba44b4abb36488c598882a6a05c69d3fbf",
    ".github/workflows/codeql.yml": "4b5364715eb1bbf0fb3611f1e5eee44852f5a5d4",
}
# The activation PR remains compatible with the existing trusted CLI. Its first
# scan uses both languages; subsequent scans admit this exact reviewed workflow.
_SELECTIVE_WORKFLOW = "bdfd6e98d59ab787babcc94ba45c129f8cd899bd"
# Exact staged selected-result workflow; install only after this policy is protected.
_RESULTS_WORKFLOW = "b5789e4b0928ef34cc3d80e8f2fa1813422b6436"
# Dormant retarget successor. The exact source must be protected before its
# workflow is deployed; a deployed successor cannot be reverted to b578.
_RETARGET_RESULTS_WORKFLOW = "8333afd10d6f32841def51970f59f038b3881d11"
# Exact staged successor pins the extractor whose finite JSON readers were
# reviewed at github/codeql a7057b836bf29767461026718b14d20790b9085f.
_PINNED_RESULTS_WORKFLOW = "6d55d0fe4e9edc86204c66e1fa3967681793a2cd"
# Dormant same-M metadata successor. Its tiny reusable job exposes native M on
# every main PR invocation; it does not replace an analysis or security gate.
_METADATA_RESULTS_WORKFLOW = "3a273057a38255ca368d3028594fb94227ba7c3b"
_METADATA_SOURCE_WORKFLOW = "d04a6dc70213d8b549bac30c11cc15eaf0182dea"
_PYTHON_POLICY_JSONS = frozenset({
    ".github/test-suite-dependencies.json",
    ".github/android-orchestration.json", ".github/test-suites.json",
})
# Ordinary metadata leaves outside both pinned extractors. This does not admit
# analysis/security controls, YAML, new paths, or a floating extractor version.
_INERT_CI_JSONS = frozenset({
    ".github/branch-cleanup.json", ".github/issue-policy.json",
    ".github/repository-health.json", ".github/dependency-releases.json",
})
# Exact 2.27.2 default extractor discovery at a7057b836bf29767461026718b14d20790b9085f:
# JS may sniff headers, but these suffixes never produce extracted source. Python
# recursive discovery follows .py/.pyw or extensionless scripts only. Existing
# leaves preserve directory-dependent startup/package-entrypoint discovery.
_PINNED_NATIVE_EXTENSIONS = frozenset({
    ".c", ".cpp", ".h", ".hpp", ".m", ".mm", ".qml", ".vert", ".frag", ".glsl",
})
_NATIVE_BLOB_BYTES = 4 * 1024 ** 2
_NATIVE_TOTAL_BYTES = 16 * 1024 ** 2
_NATIVE_BLOB_COUNT = 64
_GLOBAL_PATHS = {
    "AGENTS.md", ".gitattributes", ".gitignore", ".gitmodules", ".codeqlignore", ".tool-versions",
    "tools/repository-checks/codeql.py", "tools/repository-checks/check.py", "tools/test-evidence/inputs.py",
}
# These exact controls execute from protected policy, never the candidate.
# Pinned AutoBuild/FileExtractor at a7057b836 excludes .py from JS discovery;
# even Node shebang detection requires a suffix-free file. Python still scans
# their changed source. New paths, modes, packs and analysis controls stay full.
_PINNED_PYTHON_CONTROLS = frozenset({
    "tools/repository-checks/check.py", "tools/repository-checks/codeql.py",
    "tools/test-evidence/inputs.py",
})
_PYTHON_EXTENSIONS = {".py", ".pyw", ".pyi", ".thrift"}
_JAVASCRIPT_EXTENSIONS = {
    ".js", ".jsx", ".mjs", ".cjs", ".es6", ".es", ".xsjs", ".xsjslib",
    ".ts", ".tsx", ".mts", ".cts",
    ".htm", ".html", ".xhtm", ".xhtml", ".vue", ".hbs", ".ejs", ".njk", ".erb", ".jsp", ".dot",
    ".json", ".lock", ".raml", ".yaml", ".yml",
}
_PYTHON_MANIFESTS = {
    "pyproject.toml", "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
    ".python-version", "environment.yml", "environment.yaml", "conda-lock.yml",
}
_QUERY_EXTENSIONS = {".ql", ".qll", ".qls", ".dbscheme", ".dbscheme.stats"}
_PACK_MANIFESTS = {"qlpack.yml", "qlpack.yaml", "codeql-pack.yml", "codeql-pack.yaml", "codeql-pack.lock.yml"}
_OBJECT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def result_workflow_blobs():
    """Finite trusted selected-result generations; never candidate anchors."""
    return (_RESULTS_WORKFLOW, _RETARGET_RESULTS_WORKFLOW, _PINNED_RESULTS_WORKFLOW,
            _METADATA_RESULTS_WORKFLOW)


def pinned_workflow_entries():
    """Finite successors retaining the exact reviewed 2.27.2 extractor."""
    return [{'mode': '100644', 'type': 'blob', 'sha': oid}
            for oid in (_PINNED_RESULTS_WORKFLOW, _METADATA_RESULTS_WORKFLOW)]


def result_workflow_rollback(base_entry, candidate_entry):
    generations = [{"mode": "100644", "type": "blob", "sha": sha}
                   for sha in result_workflow_blobs()]
    return (base_entry in generations and (candidate_entry not in generations
            or generations.index(candidate_entry) < generations.index(base_entry)))


def _pinned_policy_json(change, base_tree, candidate_tree):
    """Only the fixed ordinary policy leaves are outside this exact JS extractor.

    Its TypeScript wrapper parses one selected file with noResolve and a
    compiler host that cannot read dependencies. Generic JSON is not extracted;
    ancestor configuration readers use only package.json and tsconfig names.
    Any workflow/configuration drift is rejected before this proof is used.
    """
    return (change['path'] in _PYTHON_POLICY_JSONS
            and all(tree.get('.github/workflows/codeql.yml') in pinned_workflow_entries()
                    for tree in (base_tree, candidate_tree))
            and all(isinstance(change[side], dict) and change[side]['mode'] == '100644'
                    and change[side]['type'] == 'blob' for side in ('before', 'after')))


def _pinned_ci_metadata(change, base_tree, candidate_tree):
    """Four existing generic JSON leaves supply no pinned language input.

    The reviewed JS filter excludes their names and its single-file TS parser
    cannot read imported JSON. Python traverses modules rather than these JSON
    leaves; the fixed no-build workflow executes no candidate generators.
    Whole-tree aliases, packs and actual analysis controls are checked first.
    """
    return (change['path'] in _INERT_CI_JSONS
            and all(tree.get('.github/workflows/codeql.yml') in pinned_workflow_entries()
                    for tree in (base_tree, candidate_tree))
            and all(isinstance(change[side], dict) and change[side]['mode'] == '100644'
                    and change[side]['type'] == 'blob' for side in ('before', 'after')))


def _pinned_native_source(change, base_tree, candidate_tree, read_blob):
    """A finite existing native leaf is not extracted by either pinned language.

    Raw immutable old AND new bytes are mandatory; a supplied path/tree list is
    insufficient. Additions/deletions/renames can alter directory discovery and
    retain full scans. No candidate file is opened, imported or executed here.
    """
    path = PurePosixPath(change['path'])
    if (path.suffix not in _PINNED_NATIVE_EXTENSIONS or path.name.startswith('.')
            or not callable(read_blob)
            or any(tree.get('.github/workflows/codeql.yml') not in pinned_workflow_entries()
                   for tree in (base_tree, candidate_tree))
            or any(type(change[side]) is not dict or change[side]['mode'] != '100644'
                   or change[side]['type'] != 'blob' for side in ('before', 'after'))):
        return False
    try:
        for side in ('before', 'after'):
            oid = change[side]['sha']
            raw = read_blob(oid)
            if type(raw) is not bytes or len(raw) > _NATIVE_BLOB_BYTES or b'\0' in raw:
                return False
            header = b'blob ' + str(len(raw)).encode('ascii') + b'\0'
            algorithm = hashlib.sha1 if len(oid) == 40 else hashlib.sha256
            if algorithm(header + raw).hexdigest() != oid:
                return False
            text = raw.decode('utf-8-sig')
            # Conservatively decline every shebang, regardless of interpreter,
            # suffix or executable bit; this is stronger than default discovery.
            if text.startswith('#!'):
                return False
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, TypeError):
        return False
    return True


def _native_blob_reader(root):
    """Bound immutable Git blobs by declared size, total size, count and SHA.

    This capability is internal to the trusted repository selector. Missing or
    unsupported objects decline the native exception and retain full analysis.
    """
    cache, remaining = {}, _NATIVE_TOTAL_BYTES
    def read(oid):
        nonlocal remaining
        if oid in cache:
            return cache[oid]
        if len(cache) >= _NATIVE_BLOB_COUNT or not _OBJECT.fullmatch(oid):
            raise inputs.InputError('native immutable blob inventory exceeds its bound')
        # No extractor customization can inherit this new omission. The exact
        # workflow/configuration is separately checked in both complete trees.
        if any(name.startswith(('LGTM_INDEX_', 'CODEQL_EXTRACTOR_JAVASCRIPT_OPTION_',
                                'CODEQL_EXTRACTOR_PYTHON_OPTION_')) for name in os.environ):
            raise inputs.InputError('native extractor options are unsupported')
        command = ['git', '--no-replace-objects', 'cat-file']
        size_raw = subprocess.run([*command, '-s', oid], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout
        if not re.fullmatch(rb'[0-9]{1,10}\n', size_raw):
            raise inputs.InputError('native immutable blob size is unavailable')
        size = int(size_raw)
        if size > _NATIVE_BLOB_BYTES or size > remaining:
            raise inputs.InputError('native immutable blob bytes exceed their bound')
        raw = subprocess.run([*command, 'blob', oid], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout
        if len(raw) != size:
            raise inputs.InputError('native immutable blob size changed')
        remaining -= size
        cache[oid] = raw
        return raw
    return read


def _global_input(path: str, pack_roots=()) -> bool:
    relative = PurePosixPath(path)
    name = relative.name.lower()
    return (path in _GLOBAL_PATHS or path in _REVIEWED_CONTROLS
            or any(relative.is_relative_to(root) for root in pack_roots)
            or any("codeql" in part.lower() or part.lower() in {"qlpack", "qlpacks"}
                   for part in relative.parts[:-1])
            or name in _PACK_MANIFESTS | {"codeql-config.yml", "codeql-config.yaml"}
            or relative.suffix.lower() in _QUERY_EXTENSIONS or name.endswith(".dbscheme.stats"))


def _pinned_python_control(change, base_tree, candidate_tree, pack_roots):
    """Only existing ordinary Python controls outside every custom query pack.

    Complete workflow/configuration and alias guards run before this exception.
    The same pinned workflow must remain on both sides: a deployment cannot
    certify itself. Candidate controller bytes are source, never selection code.
    """
    workflow = '.github/workflows/codeql.yml'
    return (change['path'] in _PINNED_PYTHON_CONTROLS
            and base_tree.get(workflow) == candidate_tree.get(workflow)
            and base_tree.get(workflow) in pinned_workflow_entries()
            and not any(PurePosixPath(change['path']).is_relative_to(root) for root in pack_roots)
            and not any(name.startswith(('LGTM_INDEX_', 'CODEQL_EXTRACTOR_JAVASCRIPT_OPTION_',
                                         'CODEQL_EXTRACTOR_PYTHON_OPTION_')) for name in os.environ)
            and all(type(change[side]) is dict and change[side]['mode'] == '100644'
                    and change[side]['type'] == 'blob' for side in ('before', 'after')))


def _python_requirements_manifest(name: str) -> bool:
    """Recognize named requirements without ambiguous nested repetition."""
    stem, separator, extension = name.rpartition(".")
    if not separator or extension not in {"txt", "in"}:
        return False
    for prefix in ("requirements", "constraints"):
        if stem == prefix:
            return True
        if stem.startswith(prefix):
            suffix = stem[len(prefix):]
            return (len(suffix) > 1 and suffix[0] in "-_."
                    and all(suffix[1:].split(".")))
    return False


def _source_languages(path: str) -> tuple[str, ...] | None:
    relative = PurePosixPath(path)
    name, extension = relative.name, relative.suffix.lower()
    if name in _PYTHON_MANIFESTS or _python_requirements_manifest(name):
        if extension in _JAVASCRIPT_EXTENSIONS:
            return LANGUAGES  # Lock/YAML manifests are also extracted as JS data.
        return ("python",)
    if extension in _PYTHON_EXTENSIONS:
        return ("python",)
    if extension in _JAVASCRIPT_EXTENSIONS or (name.startswith(".") and name.endswith("rc")) or name == ".xsaccess":
        return ("javascript-typescript",)
    if extension == ".md":
        return ()
    # In particular, extensionless Python/Node shebangs and arbitrary extractor
    # inputs are never assumed inert. Do not execute or import them to decide.
    return None


def _result(languages, reasons, changes) -> dict:
    ordered = [language for language in LANGUAGES if language in languages]
    return {"schema": 1, "languages": ordered, "full_scan": ordered == list(LANGUAGES),
            "reasons": reasons, "changes": changes}


def select_languages(base_tree: dict | None, candidate_tree: dict | None, *, event: str = "pull_request", read_blob=None) -> dict:
    """Select from complete trusted inputs.full_tree maps, never a PR file list.

    Unknown/malformed inventory and unsupported events request both languages.
    Rename detection is unnecessary: additions and deletions from the union of
    complete trees retain both paths, and every entry includes mode and type.
    """
    if event == "schedule":
        return _result(LANGUAGES, [{"code": "scheduled-full-scan"}], [])
    if event not in ("pull_request", "push"):
        return _result(LANGUAGES, [{"code": "unsupported-event"}], [])
    try:
        inputs._validate_tree(base_tree)
        inputs._validate_tree(candidate_tree)
    except (inputs.InputError, TypeError, ValueError):
        return _result(LANGUAGES, [{"code": "unavailable-complete-inventory"}], [])
    changes = [{"path": path, "before": dict(base_tree[path]) if path in base_tree else None,
                "after": dict(candidate_tree[path]) if path in candidate_tree else None}
               for path in sorted(base_tree.keys() | candidate_tree.keys())
               if base_tree.get(path) != candidate_tree.get(path)]
    for path, sha in _REVIEWED_CONTROLS.items():
        hashes = {sha, _SELECTIVE_WORKFLOW, *result_workflow_blobs()} if path == '.github/workflows/codeql.yml' else {sha}
        expected = [{"mode": "100644", "type": "blob", "sha": digest} for digest in hashes]
        if base_tree.get(path) not in expected or candidate_tree.get(path) not in expected:
            return _result(LANGUAGES, [{"code": "unreviewed-analysis-configuration", "path": path}], changes)
    workflow = '.github/workflows/codeql.yml'
    if result_workflow_rollback(base_tree.get(workflow), candidate_tree.get(workflow)):
        return _result(LANGUAGES, [{"code": "analysis-workflow-rollback", "path": workflow}], changes)
    if not changes:
        return _result((), [{"code": "identical-immutable-inputs"}], [])
    # Even an unchanged alias can connect, for example, source.js to source.py.
    # Until alias and submodule closures are reviewed, inspect their presence in
    # the whole tree rather than just entries reported as changed.
    for tree in (base_tree, candidate_tree):
        if any(entry["mode"] not in {"100644", "100755"} for entry in tree.values()):
            return _result(LANGUAGES, [{"code": "unresolved-source-alias-or-submodule"}], changes)
    # A pack's helpers and model data may have ordinary Python/JSON/YAML names;
    # its whole directory is shared control, including removed/renamed packs.
    pack_roots = {PurePosixPath(path).parent for path in base_tree.keys() | candidate_tree.keys()
                  if PurePosixPath(path).name.lower() in _PACK_MANIFESTS}
    python_controls = set()
    for change in changes:
        if _global_input(change['path'], pack_roots):
            if not _pinned_python_control(change, base_tree, candidate_tree, pack_roots):
                return _result(LANGUAGES, [{"code": "shared-analysis-control", "path": change['path']}], changes)
            python_controls.add(change['path'])
    languages, reasons = set(), []
    for change in changes:
        path = change["path"]
        inert_metadata = _pinned_ci_metadata(change, base_tree, candidate_tree)
        inert_native = _pinned_native_source(change, base_tree, candidate_tree, read_blob)
        if inert_metadata or inert_native:
            selected = ()
        elif _pinned_policy_json(change, base_tree, candidate_tree):
            selected = ("python",)
        else:
            selected = _source_languages(path)
        if selected is None:
            return _result(LANGUAGES, [{"code": "unknown-analysis-input", "path": path}], changes)
        languages.update(selected)
        reasons.append({"code": ("reviewed-pinned-native-source" if inert_native else
                                 "reviewed-pinned-ci-metadata" if inert_metadata else
                                 "reviewed-pinned-python-control" if path in python_controls else
                                 "language-input" if selected else "markdown-only-input"), "path": path})
    return _result(languages, reasons, changes)


def select_repository(root: Path | str, base_sha: str, candidate_sha: str, *, event: str = "pull_request") -> dict:
    """Read both immutable commits locally; missing/shallow objects stay full."""
    if event == "schedule":
        return select_languages(None, None, event=event)
    if any(not isinstance(sha, str) or not _OBJECT.fullmatch(sha) or set(sha) == {"0"}
           for sha in (base_sha, candidate_sha)):
        return _result(LANGUAGES, [{"code": "unavailable-immutable-commit"}], [])
    try:
        base_tree = inputs.full_tree(root, base_sha)
        candidate_tree = inputs.full_tree(root, candidate_sha)
    except (inputs.InputError, OSError):
        return _result(LANGUAGES, [{"code": "unavailable-complete-inventory"}], [])
    result = select_languages(base_tree, candidate_tree, event=event, read_blob=_native_blob_reader(root))
    result["commits"] = {"base": base_sha, "candidate": candidate_sha}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--candidate-sha", default="")
    parser.add_argument("--event", default="pull_request")
    args = parser.parse_args()
    print(json.dumps(select_repository(args.root, args.base_sha, args.candidate_sha, event=args.event),
                     sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
