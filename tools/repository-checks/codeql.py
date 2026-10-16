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
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re


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
_GLOBAL_PATHS = {
    "AGENTS.md", ".gitattributes", ".gitignore", ".gitmodules", ".codeqlignore", ".tool-versions",
    "tools/repository-checks/codeql.py", "tools/repository-checks/check.py", "tools/test-evidence/inputs.py",
}
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
    return (_RESULTS_WORKFLOW, _RETARGET_RESULTS_WORKFLOW)


def result_workflow_rollback(base_entry, candidate_entry):
    successor = {"mode": "100644", "type": "blob", "sha": _RETARGET_RESULTS_WORKFLOW}
    return base_entry == successor and candidate_entry != successor


def _global_input(path: str, pack_roots=()) -> bool:
    relative = PurePosixPath(path)
    name = relative.name.lower()
    return (path in _GLOBAL_PATHS or path in _REVIEWED_CONTROLS
            or any(relative.is_relative_to(root) for root in pack_roots)
            or any("codeql" in part.lower() or part.lower() in {"qlpack", "qlpacks"}
                   for part in relative.parts[:-1])
            or name in _PACK_MANIFESTS | {"codeql-config.yml", "codeql-config.yaml"}
            or relative.suffix.lower() in _QUERY_EXTENSIONS or name.endswith(".dbscheme.stats"))


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


def select_languages(base_tree: dict | None, candidate_tree: dict | None, *, event: str = "pull_request") -> dict:
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
    languages, reasons = set(), []
    for change in changes:
        path = change["path"]
        if _global_input(path, pack_roots):
            return _result(LANGUAGES, [{"code": "shared-analysis-control", "path": path}], changes)
        selected = _source_languages(path)
        if selected is None:
            return _result(LANGUAGES, [{"code": "unknown-analysis-input", "path": path}], changes)
        languages.update(selected)
        reasons.append({"code": "language-input" if selected else "markdown-only-input", "path": path})
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
    result = select_languages(base_tree, candidate_tree, event=event)
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
