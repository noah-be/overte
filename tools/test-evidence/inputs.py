#!/usr/bin/env python3
"""Fingerprint complete, trusted test input closures without running candidate code.

The registry belongs to the trusted validator. Trees describe immutable commits;
neither candidate routing metadata nor the current working directory can narrow
the inputs used to authorize reuse.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import subprocess


class InputError(ValueError):
    """An input identity cannot safely authorize reuse."""


_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_OBJECT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MODES = {"100644": "blob", "100755": "blob", "120000": "blob", "160000": "commit"}
ISOLATED_FULL_SCHEMA = 3
ISOLATED_FULL_PROFILE = "ubuntu24-isolated-host-qt5-qt6-v1"
ISOLATED_VENV = "/opt/overte-ci/venv"
ISOLATED_JDK = "/usr/lib/jvm/temurin-17-jdk-amd64"
ISOLATED_CACERTS = "/etc/ssl/certs/adoptium/cacerts"
_FULL_ENVIRONMENT_FIELDS = {"schema", "profile", "os", "python", "tools", "qt", "glm",
                            "system_packages", "flags", "trusted_execution"}
# These legacy controls remain the default for every unreviewed suite. A
# reviewed import graph can replace them with its complete directory inputs;
# changes to that graph fall back to the entire repository, including data read
# by a new import. Ordinary closure patterns keep their existing glob meaning.
_PYTHON_IMPORT_CONTROLS = frozenset({"*.py", "*.pyc", "*.pyo", "*.so", "*.pyd", "*.pth"})
_PYTHON_IMPORT_SUFFIXES = (".py", ".pyc", ".pyo", ".so", ".pyd", ".pth")


def _canonical(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise InputError("input identity must contain canonical JSON values") from error


def _path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise InputError(f"{label} must be a nonempty relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != value or value == ".":
        raise InputError(f"{label} must be a normalized relative path")
    return value


def _paths(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise InputError(f"{label} must be {'a nonempty' if nonempty else 'a'} path list")
    for item in value:
        _path(item, label)
    if len(value) != len(set(value)):
        raise InputError(f"{label} contains duplicate paths")
    return value


def _import_roots(value: object) -> list[str]:
    roots = _paths(value, "reviewed Python import roots", nonempty=True)
    if any(any(character in root for character in "*?[") for root in roots):
        raise InputError("Python import roots must be exact directories")
    return roots


def _validate_registry(registry: object) -> dict:
    if not isinstance(registry, dict) or set(registry) != {"schema", "control_inputs", "suites"}:
        raise InputError("invalid test input registry fields")
    if type(registry["schema"]) is not int or registry["schema"] != 1:
        raise InputError("unsupported test input registry schema")
    _paths(registry["control_inputs"], "control inputs", nonempty=True)
    suites = registry["suites"]
    if not isinstance(suites, dict) or not suites:
        raise InputError("registry suites must be a nonempty object")
    fields = {"command", "layer", "scope", "environment", "closure"}
    for name, suite in suites.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise InputError("invalid suite name")
        if not isinstance(suite, dict) or set(suite) not in (fields, fields | {"python_imports"}):
            raise InputError(f"invalid definition for suite {name}")
        command = suite["command"]
        if not isinstance(command, list) or not command or any(
            not isinstance(argument, str) or not argument or "\0" in argument for argument in command
        ):
            raise InputError(f"invalid command for suite {name}")
        executable = command[0]
        if "/" in executable or "\\" in executable or any(character.isspace() for character in executable):
            raise InputError(f"suite {name} command must use a canonical executable name")
        if executable.startswith("python") and executable != "python":
            raise InputError(f"suite {name} Python command must use canonical python")
        if suite["layer"] not in ("quick", "host") or suite["scope"] not in ("content", "candidate"):
            raise InputError(f"invalid execution scope for suite {name}")
        if not isinstance(suite["environment"], str) or not _NAME.fullmatch(suite["environment"]):
            raise InputError(f"invalid environment contract for suite {name}")
        closure = suite["closure"]
        if not isinstance(closure, dict) or set(closure) != {"kind", "inputs", "required"}:
            raise InputError(f"invalid input closure for suite {name}")
        if closure["kind"] not in ("patterns", "repository"):
            raise InputError(f"invalid input closure kind for suite {name}")
        _paths(closure["inputs"], f"suite {name} inputs", nonempty=closure["kind"] == "patterns")
        if closure["kind"] == "repository" and closure["inputs"]:
            raise InputError(f"repository closure for suite {name} cannot narrow its inputs")
        _paths(closure["required"], f"suite {name} required inputs")
        if any(any(character in relative for character in "*?[") for relative in closure["required"]):
            raise InputError(f"suite {name} required inputs must be exact paths")
        if closure["kind"] == "patterns" and any(
            not any(fnmatchcase(relative, pattern) for pattern in closure["inputs"])
            for relative in closure["required"]
        ):
            raise InputError(f"suite {name} required inputs must be inside its closure")
        if "python_imports" in suite:
            imports = suite["python_imports"]
            if not isinstance(imports, dict) or set(imports) != {"roots", "reviewed"}:
                raise InputError(f"invalid reviewed Python imports for suite {name}")
            roots = _import_roots(imports["roots"])
            if not isinstance(imports["reviewed"], str) or not _DIGEST.fullmatch(imports["reviewed"]):
                raise InputError(f"invalid reviewed Python import digest for suite {name}")
            if closure["kind"] != "patterns" or executable != "python" or len(command) < 2 \
                    or not command[1].endswith(".py") \
                    or command[1] not in closure["required"] or not any(
                        command[1].startswith(root + "/") for root in roots):
                raise InputError(f"suite {name} requires a reviewed Python entrypoint inside its import roots")
    _canonical(registry)
    return registry


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate registry JSON field")
        result[key] = value
    return result


def load_registry(path: Path | str) -> dict:
    """Read and strictly validate a registry from the trusted validator checkout."""
    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InputError("cannot read the trusted test input registry") from error
    return _validate_registry(registry)


def _validate_tree(tree: object) -> dict:
    if not isinstance(tree, dict):
        raise InputError("immutable tree must be a path-to-entry object")
    for path, entry in tree.items():
        _path(path, "tree path")
        if not isinstance(entry, dict) or set(entry) != {"mode", "type", "sha"}:
            raise InputError("tree entry must contain mode, type and object SHA")
        if not isinstance(entry["mode"], str) or _MODES.get(entry["mode"]) != entry["type"]:
            raise InputError("tree entry has an invalid mode or object type")
        if not isinstance(entry["sha"], str) or not _OBJECT.fullmatch(entry["sha"]):
            raise InputError("tree entry has an invalid object SHA")
    return tree


def full_tree(root: Path | str, commit: str = "HEAD") -> dict[str, dict[str, str]]:
    """Read every tracked entry of an immutable commit, including gitlinks.

    Resolve refs before enumeration. No checkout, filesystem import, candidate
    script, hook, or source-controlled command is executed.
    """
    if not isinstance(commit, str) or not commit or "\0" in commit:
        raise InputError("commit identity is invalid")
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", commit + "^{commit}"],
            cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        if not _OBJECT.fullmatch(resolved):
            raise InputError("commit did not resolve to an immutable object")
        raw = subprocess.run(
            ["git", "ls-tree", "-rz", "--full-tree", resolved], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
        tree = {}
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, sha = metadata.decode("ascii").split(" ")
            path = encoded_path.decode("utf-8", errors="strict")
            if path in tree:
                raise InputError("immutable tree contains a duplicate path")
            tree[path] = {"mode": mode, "type": object_type, "sha": sha}
    except (OSError, subprocess.CalledProcessError, ValueError, UnicodeError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError("cannot enumerate the immutable commit tree") from error
    return _validate_tree(tree)


def _selected_entries(tree: dict, patterns: list[str]) -> list[dict[str, str]]:
    return [{"path": path, **tree[path]} for path in sorted(tree)
            if any(fnmatchcase(path, pattern) for pattern in patterns)]


def selected_entries(tree: dict, patterns: list[str]) -> list[dict[str, str]]:
    """Select deterministic entries; modes, symlinks and gitlinks stay visible."""
    _validate_tree(tree)
    _paths(patterns, "input patterns")
    return _selected_entries(tree, patterns)


def _import_patterns(roots: list[str]) -> list[str]:
    # Include directory entries themselves so symlink/gitlink replacements
    # cannot disappear from a sparse immutable tree's input inventory.
    return [pattern for root in roots for pattern in (root, root + "/**")]


def _python_import_digest(tree: dict, roots: list[str]) -> str:
    modules = [item for item in _selected_entries(tree, _import_patterns(roots))
               if item["path"].endswith(_PYTHON_IMPORT_SUFFIXES)]
    return "sha256:" + hashlib.sha256(_canonical(modules)).hexdigest()


def python_import_digest(tree: dict, roots: list[str]) -> str:
    """Identify a statically reviewed complete module inventory in exact roots.

    This reads immutable path/mode/object identities, never candidate files or
    code. Reviewers must separately inspect explicit path additions, imports and
    child interpreters. Matching inventories alone do not establish that review.
    """
    _validate_tree(tree)
    return _python_import_digest(tree, _import_roots(roots))


def isolated_full_environment(environment: object) -> dict:
    """Validate recorded protected prepared identities without consumer queries.

    Only authenticated protected capture establishes these hashes. This pure
    shape check neither captures a runtime nor supplies producer authority.
    """
    if type(environment) is not dict or set(environment) != _FULL_ENVIRONMENT_FIELDS | {"prepared"} \
            or type(environment.get("schema")) is not int or environment["schema"] != ISOLATED_FULL_SCHEMA \
            or environment.get("profile") != ISOLATED_FULL_PROFILE:
        raise InputError("isolated full environment generation is incomplete")
    python = environment.get("python")
    tools = environment.get("tools")
    version = python.get("version") if type(python) is dict else None
    node = tools.get("node") if type(tools) is dict else None
    node_version = node.get("version") if type(node) is dict else None
    if type(version) is not str or not re.fullmatch(r"3\.12\.[0-9]+", version) \
            or type(node_version) is not str or not re.fullmatch(r"v22\.[0-9]+\.[0-9]+", node_version):
        raise InputError("isolated prepared tool versions are unsupported")
    prepared = environment["prepared"]
    if type(prepared) is not dict or set(prepared) != {"schema", "roots", "external_inputs"} \
            or type(prepared["schema"]) is not int or prepared["schema"] != 1 \
            or type(prepared["external_inputs"]) is not list \
            or prepared["external_inputs"] not in ([], [ISOLATED_CACERTS]):
        raise InputError("isolated prepared identity fields are incomplete")
    expected = {ISOLATED_VENV, ISOLATED_JDK,
                "/opt/hostedtoolcache/Python/" + version + "/x64",
                "/opt/hostedtoolcache/node/" + node_version[1:] + "/x64",
                *prepared["external_inputs"]}
    roots = prepared["roots"]
    if type(roots) is not dict or set(roots) != expected or any(
            type(value) is not str or not _DIGEST.fullmatch(value) for value in roots.values()):
        raise InputError("isolated prepared root inventory is incomplete or unbound")
    return prepared


def _environment(environment: object) -> dict:
    if not isinstance(environment, dict) or not environment:
        raise InputError("runtime environment identity must be a nonempty JSON object")

    def keys(value: object) -> None:
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise InputError("runtime environment JSON keys must be strings")
            for item in value.values():
                keys(item)
        elif isinstance(value, list):
            for item in value:
                keys(item)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise InputError("runtime environment must contain only JSON values")

    keys(environment)
    _canonical(environment)
    if environment.get("profile") == ISOLATED_FULL_PROFILE:
        isolated_full_environment(environment)
    return environment


def _suite_fingerprint(registry: dict, suite_name: str, tree: dict, environment: dict) -> str:
    suite = registry["suites"][suite_name]
    closure = suite["closure"]
    missing = sorted(set(closure["required"]) - set(tree))
    if missing:
        raise InputError(f"suite {suite_name} is missing required inputs")
    patterns = registry["control_inputs"]
    imports = suite.get("python_imports")
    if imports and any(item["mode"] not in ("100644", "100755")
                       for item in _selected_entries(tree, _import_patterns(imports["roots"]))):
        raise InputError(f"suite {suite_name} has an unproven Python import directory")
    reviewed = imports is not None and _python_import_digest(tree, imports["roots"]) == imports["reviewed"]
    repository = closure["kind"] == "repository" or imports is not None and not reviewed
    inputs = [{"path": path, **tree[path]} for path in sorted(tree)] if repository \
        else _selected_entries(tree, closure["inputs"] + (_import_patterns(imports["roots"]) if imports else []))
    if reviewed:
        patterns = [pattern for pattern in patterns if pattern not in _PYTHON_IMPORT_CONTROLS]
    controls = _selected_entries(tree, patterns)
    if any(item["mode"] == "120000" for item in [*inputs, *controls]):
        # A symlink blob identifies the target string, not the bytes read after
        # dereferencing it. Without an independently proven referent closure it
        # cannot authorize reuse, even when the link itself has not changed.
        raise InputError(f"suite {suite_name} has an unproven symlink input closure")
    identity = {
        "schema": 1,
        "suite": suite_name,
        "definition": suite,
        "control_inputs": controls,
        "inputs": inputs,
        "environment": environment,
    }
    return "sha256:" + hashlib.sha256(_canonical(identity)).hexdigest()


def suite_fingerprint(registry: dict, suite_name: str, tree: dict, environment: dict) -> str:
    """Bind one suite's full source/configuration closure and runtime identity."""
    _validate_registry(registry)
    if not isinstance(suite_name, str) or suite_name not in registry["suites"]:
        raise InputError("suite is not in the trusted input registry")
    _validate_tree(tree)
    _environment(environment)
    return _suite_fingerprint(registry, suite_name, tree, environment)


def plan_reuse(
    registry: dict, parent_tree: dict, candidate_tree: dict, parent_results: dict,
    parent_environment: dict, candidate_environment: dict,
) -> dict:
    """Reuse only successful proof matching independently recomputed full inputs.

    ``parent_results`` maps names to ``{status: 'passed', fingerprint: 'sha256:…'}``.
    Missing/malformed per-suite proof schedules execution. Invalid global input
    identities raise InputError, so callers must fall back rather than authorize.
    Context-sensitive suites are always required for this new candidate.
    """
    _validate_registry(registry)
    _validate_tree(parent_tree)
    _validate_tree(candidate_tree)
    _environment(parent_environment)
    _environment(candidate_environment)
    if not isinstance(parent_results, dict):
        raise InputError("parent results must be a suite-to-result object")
    if set(parent_results) - set(registry["suites"]):
        raise InputError("parent results contain an unknown suite")
    plan = {"reused": [], "required": [], "reasons": {}}
    for name, suite in registry["suites"].items():
        reason = ""
        proof = parent_results.get(name)
        if suite["scope"] == "candidate":
            reason = "candidate-context suite requires execution"
        elif not isinstance(proof, dict) or set(proof) != {"status", "fingerprint"}:
            reason = "successful parent suite proof is missing or malformed"
        elif proof["status"] != "passed" or not isinstance(proof["fingerprint"], str) \
                or not _DIGEST.fullmatch(proof["fingerprint"]):
            reason = "parent suite did not provide a successful valid fingerprint"
        else:
            try:
                parent = _suite_fingerprint(registry, name, parent_tree, parent_environment)
                candidate = _suite_fingerprint(registry, name, candidate_tree, candidate_environment)
            except InputError:
                reason = "complete suite input closure is unavailable"
            else:
                if proof["fingerprint"] != parent:
                    reason = "parent proof does not match trusted inputs and definition"
                elif parent != candidate:
                    reason = "candidate inputs or runtime environment differ"
        if reason:
            plan["required"].append(name)
            plan["reasons"][name] = reason
        else:
            plan["reused"].append(name)
            plan["reasons"][name] = "successful proof matches complete candidate inputs"
    return plan


# Separate protected impact policy. Existing schema-1 evidence and fingerprints
# deliberately retain their previous meaning and their conservative controls.
AFFECTED_POLICY = '.github/test-suite-dependencies.json'
AFFECTED_AUTHORITY = frozenset({
    AFFECTED_POLICY, '.github/test-suites.json', 'tests/platform-profile.json',
    'tests/run-project-tests.py', 'tests/run-unittest-suite.py',
    'tests/requirements-host.txt', 'tools/test-evidence/inputs.py',
    'tools/test-evidence/execution.py', 'tools/test-evidence/runtime.py',
    'tools/repository-checks/host_selection.py',
    'tools/repository-checks/android_handoff.py',
    'tools/repository-checks/android.py', 'tools/repository-checks/android_gate.py',
    'tools/repository-checks/package_checks.py', '.github/package-workflow-generations.json',
    '.github/repository-checks.json', '.github/branch-policy.json', '.github/android-owner-transfer.json',
    '.github/workflows/project-tests.yml', '.github/workflows/repository-checks.yml',
    '.github/workflows/parent-qualification.yml',
})
_AFFECTED_SETUP = frozenset({'host-full', 'python', 'git', 'qt5-qml', 'qt6-qml'})
_AFFECTED_PRODUCT_SUITES = frozenset({
    'web-entity-visibility', 'lod-preferences', 'goto-dialog-script',
    'recorded-voice-native', 'shared-script-behavior', 'device-result-schema',
    'device-jenkins', 'performance-contracts',
    'safe-landing-lifecycle',
    'embedded-web-policy',
    'account-auth-dispatch',
    'snapshot-native',
    'document-tree-native',
    'obj-material-native',
    'codeql-remediation',
    'javascript-behavior',
    'desktop-input-protocol',
    'server-console-behavior',
})
_AFFECTED_SUBJECTS = {
    'producer-proof': ('tools/test-evidence/producer.py', 'tools/test-evidence/producer-test.py', 'tools/test-evidence/execution.py', 'tools/test-evidence/inputs.py', 'tools/test-evidence/runtime.py'),
    'project-coverage': ('tests/project-coverage-test.py',),
    'native-registration': ('tests/native-registration-test.py',),
    'python-test-runner': ('tests/unittest-runner-test.py', 'tests/run-unittest-suite.py'),
}
_AFFECTED_SHARED_PROFILE = {'mode': '100644', 'type': 'blob',
                            'sha': 'd63537504c20204de9d35d9be61da72a56df59c3'}
_AFFECTED_TARGET_PROFILES = {
    'main': 'd63537504c20204de9d35d9be61da72a56df59c3',
    'apple-main': 'd63537504c20204de9d35d9be61da72a56df59c3',
    'apple-ios': 'd63537504c20204de9d35d9be61da72a56df59c3',
    'android-main': '1314006455751831be60b143e46ce9c6f5398e26',
    'android-vr': '1314006455751831be60b143e46ce9c6f5398e26',
    'android-vr-pico': '1314006455751831be60b143e46ce9c6f5398e26',
    'android-phone': 'f91169af7bdfedffb0b6ab9ab0ac1da28fd1f7fe',
}
_DEVICE_INPUTS = (
    'tests/device', 'tests/device/**', 'tests/run-unittest-suite.py',
    'tests/platform-profile.json', 'tests/requirements*.txt',
    'interface', 'interface/**', 'libraries', 'libraries/**',
    'scripts', 'scripts/**', 'domain-server', 'domain-server/**',
    'provenance', 'provenance/**', 'tools/sbom', 'tools/sbom/**',
    # The source profile can delegate this exact product launcher. Keeping the
    # complete Android component also binds its subprocess/include membership.
    'android', 'android/**',
    'ios', 'ios/**',
    'tests/javascript', 'tests/javascript/**', 'tests/performance', 'tests/performance/**',
    'tests/safe-landing', 'tests/safe-landing/**', 'tests/mocha', 'tests/mocha/**',
    'server-console', 'server-console/**', 'unpublishedScripts', 'unpublishedScripts/**',
    'tools/jsdoc', 'tools/jsdoc/**',
)


def device_reader_digest(tree, native_independent_paths):
    """Bind complete native lookup plus actual device components, never E.

    Native fixtures search ROOT itself, including extensionless headers. Every
    unknown path therefore keeps its bytes, type and mode. Only the protected
    graph's finite reviewed CI leaves may omit bytes; their membership/modes
    remain bound and component inputs always override that independence proof.
    """
    _validate_tree(tree)
    components = {item['path'] for item in _selected_entries(tree, list(_DEVICE_INPUTS))}
    independent = set(native_independent_paths)
    entries = []
    for path, entry in sorted(tree.items()):
        item = {'path': path, **entry}
        if path in independent and path not in components:
            item.pop('sha')
        entries.append(item)
    return 'sha256:' + hashlib.sha256(_canonical(entries)).hexdigest()


def affected_lookup_digest(tree):
    """Bind possible import names/modes everywhere and root module contents.

    Python lookup/discovery roots inside each component are also fully bound.
    An added shadow, package, native extension or .pth cannot inherit the graph.
    Hyphenated scripts outside discovery roots are not importable module names.
    """
    _validate_tree(tree)
    candidates = []
    root_modules = []
    for path, entry in sorted(tree.items()):
        name = path.rsplit('/', 1)[-1]
        if path.endswith(_PYTHON_IMPORT_SUFFIXES) and (name.split('.')[0].isidentifier() or path.endswith('.pth')):
            candidates.append({'path': path, 'mode': entry['mode'], 'type': entry['type']})
            if '/' not in path:
                root_modules.append({'path': path, **entry})
    return 'sha256:' + hashlib.sha256(_canonical({'membership': candidates, 'root_modules': root_modules})).hexdigest()


def _suite_definition_digest(suite):
    return 'sha256:' + hashlib.sha256(_canonical(suite)).hexdigest()


def _validate_dependencies(value, registry):
    _validate_registry(registry)
    if not isinstance(value, dict) or type(value.get('schema')) is not int \
            or value['schema'] not in {1, 2} \
            or set(value) != {'schema', 'registry_digest', 'lookup_digest', 'suites'} | ({'targets'} if value['schema'] == 2 else set()) \
            or value['registry_digest'] != 'sha256:' + hashlib.sha256(_canonical(registry)).hexdigest() \
            or not isinstance(value['lookup_digest'], str) or not _DIGEST.fullmatch(value['lookup_digest']) \
            or not isinstance(value['suites'], dict) or set(value['suites']) != set(registry['suites']):
        raise InputError('incomplete protected suite dependency policy')
    if value['schema'] == 2:
        targets = value['targets']
        if type(targets) is not dict or set(targets) != set(_AFFECTED_TARGET_PROFILES):
            raise InputError('seven-target dependencies require the complete finite target inventory')
        for target, row in targets.items():
            profile = {'mode': '100644', 'type': 'blob', 'sha': _AFFECTED_TARGET_PROFILES[target]}
            if type(row) is not dict or set(row) != {'profile', 'lookup_digest', 'reader_digest'} \
                    or row['profile'] != profile or any(type(row[key]) is not str or not _DIGEST.fullmatch(row[key])
                        for key in ('lookup_digest', 'reader_digest')):
                raise InputError('seven-target dependency identity is incomplete or has an unknown profile')
        native = value['suites'].get('device-control-plane-full')
        if type(native) is not dict or targets['main']['lookup_digest'] != value['lookup_digest'] \
                or targets['main']['reader_digest'] != native.get('reviewed_reader_digest'):
            raise InputError('seven-target default source identity differs from its main reader')
    for name, row in value['suites'].items():
        suite = registry['suites'][name]
        if not isinstance(row, dict) or set(row) not in (
                {'kind', 'definition_digest', 'setup'},
                {'kind', 'definition_digest', 'setup', 'reviewed_reader_digest', 'native_independent_paths'}) \
                or type(row['kind']) is not str or row['kind'] not in {'repository', 'reviewed-patterns', 'device-control-plane', 'reviewed-product-inventory', 'reviewed-subject-inventory'} \
                or row['definition_digest'] != _suite_definition_digest(suite) \
                or not isinstance(row['setup'], list) or not row['setup'] \
                or any(type(item) is not str or item not in _AFFECTED_SETUP for item in row['setup']) \
                or len(row['setup']) != len(set(row['setup'])):
            raise InputError('unsupported protected suite dependency definition')
        if row['kind'] == 'reviewed-patterns' and (suite['closure']['kind'] != 'patterns'
                or 'python_imports' not in suite):
            raise InputError('finite suite dependency requires its reviewed import closure')
        if row['kind'] == 'repository' and row['setup'] != ['host-full']:
            raise InputError('unproved suite must retain complete host preparation')
        if row['kind'] == 'reviewed-product-inventory' and (name not in _AFFECTED_PRODUCT_SUITES
                or suite['scope'] != 'content' or row['setup'] != ['host-full']):
            raise InputError('unsupported reviewed product inventory owner')
        if row['kind'] == 'reviewed-subject-inventory' and (name not in _AFFECTED_SUBJECTS
                or suite['scope'] != 'content' or row['setup'] != ['host-full']
                or tuple(suite['closure']['required']) != _AFFECTED_SUBJECTS[name]):
            raise InputError('unsupported reviewed fixed-subject owner')
        if row['kind'] == 'device-control-plane':
            if name != 'device-control-plane-full' or suite['scope'] != 'content' \
                    or not (suite['command'][:5] == ['python', 'tests/device/run_control_plane_tests.py', '--profile', 'full', '--require-qml'] \
                            or suite['command'][:8] == ['python', '-I', '-S', '-B', 'tests/device/run_control_plane_tests.py', '--profile', 'full', '--require-qml']) \
                    or set(row) != {'kind', 'definition_digest', 'setup', 'reviewed_reader_digest', 'native_independent_paths'} \
                    or row['setup'] != ['host-full'] or not isinstance(row['reviewed_reader_digest'], str) \
                    or not _DIGEST.fullmatch(row['reviewed_reader_digest']):
                raise InputError('unsupported reviewed device control-plane dependency')
            paths = _paths(row['native_independent_paths'], 'reviewed independent native lookup leaves', nonempty=True)
            if len(paths) > 1000 or AFFECTED_POLICY not in paths or any(
                    any(character in path for character in '*?[') for path in paths):
                raise InputError('native lookup independence requires finite exact protected leaves')
        elif 'reviewed_reader_digest' in row or 'native_independent_paths' in row:
            raise InputError('reader identity belongs only to the fixed device owner')
    if any(row['kind'] in {'reviewed-product-inventory', 'reviewed-subject-inventory'}
           for row in value['suites'].values()) \
            and value['suites'].get('device-control-plane-full', {}).get('kind') != 'device-control-plane':
        raise InputError('reviewed product owners require the fixed complete native inventory')
    return value


def load_dependencies(path, registry):
    """Read only the fixed protected manifest; caller authenticates its blob."""
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
            raise InputError('protected suite dependency policy is unavailable')
        raw = path.read_bytes()
        if len(raw) > 64_000:
            raise InputError('protected suite dependency policy exceeds its bound')
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as error:
        raise InputError('protected suite dependency policy is invalid') from error
    _validate_dependencies(value, registry)
    return raw


def plan_affected(registry, dependency_bytes, base_tree, candidate_tree, trusted_tree, *, target='main'):
    """Pure affected-suite selection from complete authenticated immutable trees.

    No candidate program, supplied subset, receipt or runtime query is used.
    This supplies no passing/reuse proof. A missing or changed protected graph,
    selector, registry, execution authority or nonregular inventory is unavailable.
    The caller retains its independently validated legacy gate on InputError.
    """
    _validate_registry(registry)
    if type(dependency_bytes) is not bytes or len(dependency_bytes) > 64_000:
        raise InputError('protected dependency bytes are unavailable')
    try:
        dependencies = _validate_dependencies(json.loads(dependency_bytes, object_pairs_hook=_unique_object), registry)
    except (UnicodeError, ValueError) as error:
        raise InputError('protected dependency bytes are invalid') from error
    target_row = None
    if dependencies['schema'] == 2:
        if type(target) is not str or target not in _AFFECTED_TARGET_PROFILES:
            raise InputError('unknown seven-target dependency context')
        target_row = dependencies['targets'][target]
    contexts = ((base_tree, target_row), (candidate_tree, target_row),
        (trusted_tree, dependencies['targets']['main'] if target_row is not None else None))
    for tree, context in contexts:
        _validate_tree(tree)
        if any(e['mode'] not in {'100644', '100755'} or e['type'] != 'blob' for e in tree.values()):
            raise InputError('affected selection requires complete ordinary inventories')
        lookup = context['lookup_digest'] if context is not None else dependencies['lookup_digest']
        profile = context['profile'] if context is not None else _AFFECTED_SHARED_PROFILE
        if affected_lookup_digest(tree) != lookup:
            raise InputError('affected selection lookup membership is not reviewed')
        if tree.get('tests/platform-profile.json') != profile:
            raise InputError('affected selection requires the exact reviewed target platform profile'
                if context is not None else 'affected selection requires the exact empty shared platform profile')
    entry = {'mode': '100644', 'type': 'blob', 'sha': hashlib.sha1(
        b'blob ' + str(len(dependency_bytes)).encode('ascii') + b'\0' + dependency_bytes).hexdigest()}
    if any(tree.get(AFFECTED_POLICY) != entry for tree in (base_tree, candidate_tree, trusted_tree)):
        raise InputError('dependency graph must already be identical protected policy')
    for path in AFFECTED_AUTHORITY:
        if target_row is not None and path == 'tests/platform-profile.json':
            continue  # Its three independent finite entries were checked above.
        actual = trusted_tree.get(path)
        mode = '100755' if path == 'tests/run-project-tests.py' else '100644'
        if actual is None or actual['mode'] != mode or actual['type'] != 'blob' \
                or any(tree.get(path) != actual for tree in (base_tree, candidate_tree)):
            raise InputError('affected selection authority differs from protected source')
    if trusted_tree['.github/test-suites.json']['mode'] != '100644' \
            or trusted_tree['.github/test-suites.json']['type'] != 'blob':
        raise InputError('trusted suite registry must remain ordinary')
    paths = sorted(p for p in base_tree.keys() | candidate_tree.keys() if base_tree.get(p) != candidate_tree.get(p))
    if not paths:
        raise InputError('affected selection requires a real immutable delta')
    controls = [p for p in registry['control_inputs']
                if p not in _PYTHON_IMPORT_CONTROLS and p != 'tools/test-evidence/**']
    required, omitted, reasons, setup = [], [], {}, set()
    native_row = dependencies['suites'].get('device-control-plane-full', {})
    native_digest = target_row['reader_digest'] if target_row is not None else native_row.get('reviewed_reader_digest')
    native_unchanged = native_row.get('kind') == 'device-control-plane' and all(
        device_reader_digest(tree, native_row['native_independent_paths']) == native_digest
        for tree in (base_tree, candidate_tree))
    for name, suite in registry['suites'].items():
        row = dependencies['suites'][name]
        reason = 'candidate-scope' if suite['scope'] == 'candidate' else 'unproved-repository-reader'
        unaffected = False
        if suite['scope'] == 'content' and row['kind'] == 'reviewed-patterns':
            closure, imports = suite['closure'], suite['python_imports']
            complete = all(all(path in tree for path in closure['required'])
                           and _python_import_digest(tree, imports['roots']) == imports['reviewed']
                           for tree in (base_tree, candidate_tree))
            if complete:
                # Preserve complete import-root bytes and negative membership,
                # including neighboring data and native/import shadow candidates.
                patterns = [*closure['inputs'], *_import_patterns(imports['roots']), *controls]
                unaffected = _selected_entries(base_tree, patterns) == _selected_entries(candidate_tree, patterns)
                reason = 'unchanged-reviewed-dependencies' if unaffected else 'changed-reviewed-dependencies'
            else:
                reason = 'unreviewed-import-or-missing-required-input'
        elif row['kind'] in {'device-control-plane', 'reviewed-product-inventory'}:
            unaffected = native_unchanged and all(all(path in tree for path in suite['closure']['required'])
                                                 for tree in (base_tree, candidate_tree))
            reason = 'unchanged-reviewed-product-components' if unaffected else 'product-component-or-reader-not-reviewed'
        elif row['kind'] == 'reviewed-subject-inventory':
            # Required[] is normally an existence check. These fixed CI readers
            # also need every actual subject's bytes/mode in all three trees,
            # since the shared native inventory omits independent CI leaf bytes.
            unaffected = native_unchanged and all(
                path in trusted_tree and all(tree.get(path) == trusted_tree[path]
                    for tree in (base_tree, candidate_tree))
                for path in _AFFECTED_SUBJECTS[name])
            reason = 'unchanged-reviewed-fixed-subjects' if unaffected else 'fixed-subject-or-reader-not-reviewed'
        if unaffected:
            omitted.append(name)
        else:
            required.append(name)
            setup.update(row['setup'])
        reasons[name] = reason
    return {'schema': 1, 'kind': 'affected-suite-selection', 'reusable': False,
            'required': required, 'omitted': omitted, 'reasons': reasons,
            'paths': paths, 'dependency_digest': 'sha256:' + hashlib.sha256(dependency_bytes).hexdigest(),
            'required_setup': ['host-full'] if 'host-full' in setup else sorted(setup),
            **({'dependency_schema': 2, 'target': target} if target_row is not None else {})}
