#!/usr/bin/env python3
"""Dormant original-environment admission; never capture an unused consumer VM.

Environment admission and source planning do NOT authenticate JSON. The terminal
revalidates the existing legacy gate's API facts twice; it does not strengthen
that gate's archive/source/uploader guarantees. Activation remains blocked on
their separate implementation and review, even if trusted policy is enabled.
There is no CLI switch, implicit execution, fallback, dispatch or workflow hook.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import execution
import inputs
import runtime


ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/attested-runtime.json"
PRODUCER = "overte-attested-shared-reuse-v1"
# Source-level blocker: enabling JSON policy cannot repair legacy API/source/
# uploader guarantees. Remove only with reviewed authenticated-owner integration.
ACTIVATION_READY = False
# Separate source qualification for the protected /work profile. Its trusted
# policy must also bind the exact namespace locale and safe-directory override;
# this capability never enables the legacy terminal above.
ISOLATED_ADMISSION_READY = False
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)+(?:[-+][A-Za-z0-9_.-]+)?\Z")
_PYTHON_FLAGS = {
    "bytes_warning": 0, "debug": 0, "dev_mode": False, "dont_write_bytecode": 0,
    "hash_randomization": 1, "ignore_environment": 0, "inspect": 0, "interactive": 0,
    "isolated": 0, "no_site": 0, "no_user_site": 0, "optimize": 0, "quiet": 0,
    "safe_path": False, "utf8_mode": 0, "verbose": 0, "warn_default_encoding": 0,
}
_FLAGS = set(runtime._CHOICES) | {
    "git_process_overrides", "JAVA_HOME", "OVERTE_QML_TEST_RUNNER", "PKG_CONFIG_PATH",
    "LD_LIBRARY_PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
}
_CONSUMER_FILES = (
    POLICY, ".github/test-suites.json", ".github/sync-test-reuse.json",
    ".github/branch-policy.json", ".github/repository-checks.json", ".github/package-workflow-generations.json",
    "tools/test-evidence/attested.py", "tools/test-evidence/validate-sync.py",
    "tools/sync-test-reuse/gate.py", "tools/sync-test-reuse/differential.py",
    "tools/branch-policy/check.py", "tools/repository-checks/check.py",
    "tools/repository-checks/package_checks.py", "tools/repository-checks/tool_dependencies.py",
    "tools/test-evidence/postmerge.py", "tools/test-evidence/producer_workflow.py",
    "tools/test-evidence/producer.py", "tools/test-evidence/producer_api.py",
    "tools/repository-checks/workflows/producers/parent-qualification.yml",
)


class AttestedReuseUnavailable(ValueError):
    """No zero-execution result can be established; the caller owns fallback."""


def require(condition, message):
    if not condition:
        raise AttestedReuseUnavailable(message)


def _fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names), "unsupported recorded runtime fields")


def _digest(value):
    return "sha256:" + hashlib.sha256(inputs._canonical(value)).hexdigest()


def _hash(value):
    require(isinstance(value, str) and _DIGEST.fullmatch(value), "missing recorded runtime digest")


def _text(value, pattern, limit=500):
    require(isinstance(value, str) and 0 < len(value) <= limit and re.fullmatch(pattern, value),
            "unsupported recorded runtime identity")


def _time(value):
    try:
        require(isinstance(value, str) and value.endswith("Z"), "runtime proof requires original UTC times")
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise AttestedReuseUnavailable("runtime proof has an invalid UTC time") from None


def _bytes(root, relative, maximum=1_000_000):
    path = root
    for component in Path(relative).parts:
        path /= component
        require(not path.is_symlink(), "trusted runtime policy cannot contain aliases")
    try:
        require(path.is_file() and path.stat().st_size <= maximum, "trusted runtime policy is unavailable")
        value = path.read_bytes()
    except OSError:
        raise AttestedReuseUnavailable("trusted runtime policy is unavailable") from None
    require(len(value) <= maximum, "trusted runtime policy exceeds its byte bound")
    return value


def load_policy(root=ROOT, *, isolated=False):
    """Read only a trusted checkout's fixed default-off policy, never candidate data."""
    require(not isolated or ISOLATED_ADMISSION_READY, 'isolated runtime admission is not qualified')
    try:
        value = json.loads(_bytes(Path(root), POLICY, 32_000), object_pairs_hook=inputs._unique_object)
    except (ValueError, UnicodeError):
        raise AttestedReuseUnavailable("trusted attested-runtime policy is invalid") from None
    _fields(value, {"schema", "enabled", "epoch", "not_before", "max_age_seconds", "flags"})
    require(type(value["schema"]) is int and value["schema"] == 1 and type(value["enabled"]) is bool,
            "unsupported attested-runtime policy")
    _text(value["epoch"], r"[a-z0-9][a-z0-9-]*", 100)
    _time(value["not_before"])
    require(type(value["max_age_seconds"]) is int and 0 < value["max_age_seconds"] <= 259200,
            "unsupported runtime validity policy")
    _fields(value["flags"], _FLAGS)
    require(all(isinstance(item, str) for item in value["flags"].values()), "unsupported runtime flag policy")
    for name, (choices, _) in runtime._CHOICES.items():
        require(value["flags"][name] in choices, "unsupported reviewed runtime variant")
    require(value["flags"]["git_process_overrides"] == (
                "maintenance-disabled-safe-work" if isolated else "maintenance-disabled")
            and value["flags"]["JAVA_HOME"] == "identified-jdk"
            and value["flags"]["OVERTE_QML_TEST_RUNNER"] in {"Qt5", "Qt6"}
            and value["flags"]["PKG_CONFIG_PATH"] in {"system", "python-base-pkgconfig"}
            and value["flags"]["LD_LIBRARY_PATH"] in {"system", "python-base-lib"}, "unsupported runtime flag policy")
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "TZ"):
        require(not value["flags"][name] or re.fullmatch(r"[A-Za-z0-9_.+/@:-]{1,100}", value["flags"][name]),
                "unsupported runtime locale policy")
    if isolated:
        require({name: value["flags"][name] for name in ("LANG", "LC_ALL", "LC_CTYPE", "TZ")} == {
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "LC_CTYPE": "", "TZ": ""},
            "isolated runtime policy differs from the fixed namespace locale")
    require(value["enabled"] is True, "attested runtime reuse is disabled by trusted policy")
    return value


def _policy_identity(root, policy, manifests):
    files = {path: "sha256:" + hashlib.sha256(_bytes(root, path)).hexdigest()
             for path in {*runtime._TRUSTED_EXECUTION_FILES, *_CONSUMER_FILES, *manifests}}
    return {"epoch": policy["epoch"], "digest": _digest({"policy": policy, "files": files})}


def validate_environment(environment, qualified_at, expires_at, now, *, root=ROOT, isolated=False):
    """Admit an ORIGINAL recorded identity; this pure check supplies no provenance.

    All recorded values remain exact fingerprint inputs. Matching shape, policy
    or this return value cannot authenticate a producer or a passed test.
    """
    root = Path(root)
    policy = load_policy(root, isolated=isolated)
    require(isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset().total_seconds() == 0,
            "runtime admission requires an independent current UTC clock")
    qualified, expires = _time(qualified_at), _time(expires_at)
    require(_time(policy["not_before"]) <= qualified <= now < expires
            and (expires - qualified).total_seconds() <= policy["max_age_seconds"],
            "original runtime proof is expired or outside the reviewed epoch")
    if isolated:
        try:
            inputs.isolated_full_environment(environment)
        except inputs.InputError as error:
            raise AttestedReuseUnavailable("original isolated prepared environment is incomplete") from error
    inputs._environment(environment)
    require(len(inputs._canonical(environment)) <= 2_000_000, "recorded runtime exceeds its byte bound")
    _fields(environment, {"schema", "profile", "os", "python", "tools", "qt", "glm", "system_packages", "flags", "trusted_execution"}
            | ({"prepared"} if isolated else set()))
    require(type(environment["schema"]) is int and environment["schema"] == (inputs.ISOLATED_FULL_SCHEMA if isolated else 1)
            and environment["profile"] == (inputs.ISOLATED_FULL_PROFILE if isolated else "ubuntu24-host-qt5-qt6-v1"),
            "unsupported original runtime generation")
    operating = environment["os"]
    _fields(operating, {"architecture", "distribution", "kernel", "namespace", "runner", "timezone_digest", "version"})
    require((operating["distribution"], operating["version"], operating["architecture"]) == ("ubuntu", "24.04", "x86_64"),
            "original OS profile is unsupported")
    _text(operating["kernel"], r"[A-Za-z0-9._+-]+", 200)
    _hash(operating["timezone_digest"])
    _fields(operating["runner"], {"ImageOS", "ImageVersion", "RUNNER_ENVIRONMENT"})
    require(operating["runner"]["ImageOS"] == "ubuntu24" and operating["runner"]["RUNNER_ENVIRONMENT"] == "github-hosted",
            "original runner profile is unsupported")
    _text(operating["runner"]["ImageVersion"], r"[0-9]+(?:\.[0-9]+)+", 100)
    _fields(operating["namespace"], {"apparmor_restrict_unprivileged_userns", "max_user_namespaces"})
    require(operating["namespace"]["apparmor_restrict_unprivileged_userns"] == "0", "original isolation profile is unsupported")
    _text(operating["namespace"]["max_user_namespaces"], r"[0-9]+", 20)
    require(int(operating["namespace"]["max_user_namespaces"]) > 0, "original user namespaces were unavailable")
    python = environment["python"]
    _fields(python, {"implementation", "version", "executable_digest", "library_digest", "flags", "packages", "process_lookup"})
    require(python["implementation"] == "CPython", "original Python implementation is unsupported")
    _text(python["version"], r"3\.12\.[0-9]+", 50)
    _hash(python["executable_digest"]); _hash(python["library_digest"])
    require(inputs._canonical(python["flags"]) == inputs._canonical(_PYTHON_FLAGS), "unsupported original Python flags")
    require(inputs._canonical(python["process_lookup"]) == inputs._canonical({
        "aliases": ["python", "python3"], "include_system_site_packages": False,
        "mode": "controller-virtualenv", "user_site_enabled": False}), "unbound original Python lookup environment")
    required, manifests = runtime._requirement_inventory(root)
    packages = python["packages"]
    require(isinstance(packages, dict) and 0 < len(packages) <= 2000, "original Python package inventory is incomplete")
    for name, version in packages.items():
        _text(name, r"[a-z0-9][a-z0-9-]*", 200)
        _text(version, r"[A-Za-z0-9][A-Za-z0-9_.+!-]*", 200)
    require(all(packages.get(name) == version for name, version in required.items()), "original Python packages differ from current exact pins")
    _fields(environment["tools"], runtime._COMMANDS)
    for tool in environment["tools"].values():
        _fields(tool, {"version", "executable_digest"})
        _text(tool["version"], r"[A-Za-z0-9 ._+():,/'\";=\[\]~@-]+")
        _hash(tool["executable_digest"])
    versions = environment["tools"]
    require(re.fullmatch(r"v22\.[0-9]+\.[0-9]+", versions["node"]["version"])
            and re.fullmatch(r"10\.[0-9]+\.[0-9]+", versions["npm"]["version"])
            and re.fullmatch(r"openjdk 17\.[0-9.]+ [0-9-]+", versions["java"]["version"])
            and re.fullmatch(r"javac 17\.[0-9.]+", versions["javac"]["version"]), "original Node/npm/JDK profile is unsupported")
    _fields(environment["qt"], {"modules", "tools"})
    _fields(environment["qt"]["modules"], runtime._QT_MODULES)
    for module, version in environment["qt"]["modules"].items():
        require(isinstance(version, str) and _VERSION.fullmatch(version)
                and version.startswith("5.15." if module.startswith("Qt5") else "6.4."), "original Qt profile is unsupported")
    _fields(environment["qt"]["tools"], {"Qt5-moc", "Qt6-moc", "qmltestrunner"})
    for value in environment["qt"]["tools"].values(): _hash(value)
    _fields(environment["glm"], {"header_digest", "configuration_digest"})
    for value in environment["glm"].values(): _hash(value)
    system = environment["system_packages"]
    require(isinstance(system, dict) and 0 < len(system) <= 10000, "original system package inventory is incomplete")
    for name, version in system.items():
        _text(name, r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?", 200)
        _text(version, r"[A-Za-z0-9.+:~_-]+", 200)
    require(any(name.split(":", 1)[0] == "libglm-dev" for name in system), "original GLM package is unavailable")
    require(environment["flags"] == policy["flags"], "original flags or fixture variants differ from reviewed policy")
    expected = runtime._controller_file_hashes(manifests, root)
    require(environment["trusted_execution"] == expected, "original controller, requirement or admission-policy bytes changed")
    return {"environment_digest": _digest(environment), "policy": _policy_identity(root, policy, manifests)}


def plan_zero_shared(registry, parent_tree, candidate_tree, parent_results, environment):
    """Pure source plan only; no argument type or resulting plan authenticates proof."""
    plan = inputs.plan_reuse(registry, parent_tree, candidate_tree, parent_results, environment, environment)
    require(not plan["required"] and set(plan["reused"]) == set(registry["suites"]),
            "zero-shared terminal requires complete unchanged shared suite proof")
    return plan


def _validation():
    spec = importlib.util.spec_from_file_location("attested_sync_validation", ROOT / "tools/test-evidence/validate-sync.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _empty_products(candidate, registry, tree):
    relative = "tests/platform-profile.json"
    entry = tree.get(relative, {})
    require(entry.get("mode") == "100644" and entry.get("type") == "blob", "product profile is not an ordinary immutable input")
    raw = _bytes(candidate, relative, 100_000)
    require(not (candidate / relative).stat().st_mode & 0o111
            and hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == entry.get("sha"),
            "materialized product profile differs from its immutable Git blob")
    require(not execution.platform_suites(candidate, registry["suites"]), "declared product suites require a separate successful owner")


def verify_zero_shared_sync(args, *, api=None, root=ROOT, clock=lambda: datetime.now(timezone.utc)):
    """Dormant terminal: repeat legacy gate checks; never execute shared/product suites.

    The fixed trusted policy must be enabled; no caller-supplied proof boolean,
    CLI enable flag or candidate policy can bypass it. No workflow calls this.
    Unsupported/partial proof raises; this helper neither retries nor falls back.
    """
    root = Path(root)
    load_policy(root)
    require(ACTIVATION_READY, "attested terminal activation blocked pending authenticated producer integration")
    validation = _validation()
    gate = validation._gate()
    config = gate.load_config()
    api = api or gate.GitHubApi()
    require(args.mode == "reuse", "attested terminal does not own fallback execution")
    request = validation._request(args, gate, config, api)
    require(request.profile not in {"documentation", "tool-dependencies"}, "bounded profiles retain their existing independent owners")
    candidate = Path(args.candidate).resolve(strict=True)
    initial = execution.checkout_identity(candidate)
    require(initial[0] == request.merge_sha, "attested candidate differs from the exact live merge")
    tree = inputs.full_tree(candidate, initial[0])
    registry = inputs.load_registry(root / ".github/test-suites.json")
    _empty_products(candidate, registry, tree)
    evidence = gate.verify_evidence(api, config, request, now=clock())
    require(evidence.get("candidate_inputs") == tree, "local candidate differs from independently verified API inputs")
    admission = validate_environment(evidence["environment"], evidence["qualified_at"], evidence["expires_at"], clock(), root=root)
    plan = plan_zero_shared(registry, evidence["parent_inputs"], tree, evidence["results"]["suites"], evidence["environment"])
    started = clock().isoformat().replace("+00:00", "Z")
    validation._candidate_differential(candidate, request, gate, api)
    require(execution.checkout_identity(candidate) == initial, "candidate changed during differential checks")
    require(validation._request(args, gate, config, api) == request, "live synchronization classification changed")
    final = gate.verify_evidence(api, config, request, now=clock())
    require(final == evidence, "original parent authority or evidence changed during attested verification")
    require(validate_environment(final["environment"], final["qualified_at"], final["expires_at"], clock(), root=root) == admission,
            "trusted runtime policy changed during attested verification")
    require(plan_zero_shared(registry, final["parent_inputs"], tree, final["results"]["suites"], final["environment"]) == plan,
            "complete shared input plan changed during verification")
    validation._recheck(api, gate, request)
    require(execution.checkout_identity(candidate) == initial, "candidate changed during final API checks")
    _empty_products(candidate, registry, tree)
    validation._bounded_junit(args.junit, [])  # Exactly one actually executed differential; no fake suite passes.
    completed = clock()
    require(completed < _time(evidence["expires_at"]), "original parent evidence expired before terminal completion")
    value = {
        "schema": 1, "producer": PRODUCER, "repository": request.repository, "repository_id": request.repository_id,
        "pull_request": request.number, "candidate_commit": initial[0], "candidate_tree": initial[1],
        "base_commit": request.base_sha, "head_commit": request.head_sha, "mode": "attested-reuse",
        "reused_suites": plan["reused"], "executed_suites": [], "platform_results": {},
        "execution": None, "consumer_environment": None, "original_environment_digest": admission["environment_digest"],
        "runtime_admission": admission["policy"], "parent_evidence": validation._parent_provenance(evidence, plan["reused"]),
        "conclusion": "success", "started_at": started, "completed_at": completed.isoformat().replace("+00:00", "Z"),
    }
    value["receipt_digest"] = execution.digest(value)
    execution._write_receipt(args.receipt, value)
    return value
