#!/usr/bin/env python3
"""Dormant trusted Android suite ownership, execution and complete-result proofs.

The policy is read from this reviewed checkout. Candidate catalogs are bounded
input data and cannot choose the mandatory inventory. No input-based reuse or
branch activation is implemented here: every selected owner actually executes.
Receipt hashes establish consistency, not remote workflow provenance. Callers
must use the trusted controller workspace or authenticate artifact provenance.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = "overte-trusted-android-execution-v1"
VIEWS = ("fast", "contracts", "coverage", "android-vr", "pico", "mutation")
DEFAULT_VIEWS = list(VIEWS[:-1])
MAX_SOURCE_BYTES = 2_000_000
EXECUTION_FILES = ("tools/repository-checks/android.py", "tools/test-evidence/execution.py",
                   "tools/test-evidence/runtime.py", "tools/test-evidence/inputs.py", "tests/run-project-tests.py")
TOOLS = {"bash": ("bash", "--version"), "java": ("java", "--version"),
         "javac": ("javac", "--version"), "node": ("node", "--version"),
         "compiler": ("c++", "--version"), "cmake": ("cmake", "--version"),
         "ctest": ("ctest", "--version"), "git": ("git", "--version"), "jq": ("jq", "--version"),
         "npm": ("npm", "--version"), "gcov": ("gcov", "--version")}


class AndroidError(ValueError):
    """The required Android execution or its proof cannot be established."""


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise AndroidError("duplicate JSON field")
        result[name] = value
    return result


def _json(path):
    try:
        if path.is_symlink() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise AndroidError("unsafe or oversized JSON input")
        return json.loads(path.read_text(), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AndroidError("required Android JSON input is unavailable") from error


def _file(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise AndroidError("invalid Android input path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or relative.startswith("-"):
        raise AndroidError("Android input escapes its checkout")
    path = root
    for component in parts.parts:
        path = path / component
        if path.is_symlink():
            raise AndroidError("Android input contains a symbolic link")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise AndroidError("required Android source input is unavailable")
    return path


def _shared():
    directory = ROOT / "tools/test-evidence"
    sys.path.insert(0, str(directory))
    try:
        import execution
        import runtime
    finally:
        sys.path.pop(0)
    if Path(execution.__file__).resolve() != directory / "execution.py" \
            or Path(runtime.__file__).resolve() != directory / "runtime.py":
        raise AndroidError("Android controller imported an untrusted execution helper")
    return execution, runtime


class _GitSources:
    """Bounded regular blobs from one fixed commit, independent of sparse files."""

    def __init__(self, candidate, commit, tree, shared):
        self.candidate = candidate
        self.sizes = {}
        self.contents = {}
        # Replacement refs must not substitute another tree or blob for the
        # immutable commit named in the plan. No candidate hooks or filters run.
        actual_tree = self._git("rev-parse", "--verify", commit + "^{tree}").decode("ascii").strip()
        if actual_tree != tree:
            raise AndroidError("Android commit tree differs from its checkout identity")
        entries = {}
        try:
            for record in self._git("ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
                if not record:
                    continue
                metadata, path = record.split(b"\t", 1)
                mode, kind, sha = metadata.decode("ascii").split(" ")
                relative = path.decode("utf-8", errors="strict")
                if relative in entries:
                    raise AndroidError("duplicate Android Git source path")
                entries[relative] = {"mode": mode, "type": kind, "sha": sha}
            self.entries = shared.inputs._validate_tree(entries)
        except (ValueError, UnicodeError) as error:
            raise AndroidError("invalid immutable Android source tree") from error

    def _git(self, *arguments, data=None):
        try:
            return subprocess.run(["git", "--no-replace-objects", *arguments], cwd=self.candidate,
                input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise AndroidError("immutable Android Git source is unavailable") from error

    def require(self, paths):
        pending = {}
        for relative in paths:
            entry = self.entries.get(relative)
            if entry is None:
                raise AndroidError("required Android Git source is missing")
            if entry["mode"] not in {"100644", "100755"} or entry["type"] != "blob":
                raise AndroidError("required Android Git source is not a regular blob")
            if entry["sha"] not in self.sizes:
                pending[entry["sha"]] = None
        if not pending:
            return
        # Check object size before reading contents, including entrypoints that
        # only need an existence/mode check. Read no candidate-provided command.
        identities = list(pending)
        lines = self._git("cat-file", "--batch-check",
                          data="".join(sha + "\n" for sha in identities).encode("ascii")).splitlines()
        if len(lines) != len(identities):
            raise AndroidError("incomplete Android Git source inventory")
        for sha, line in zip(identities, lines):
            match = re.fullmatch(rb"([0-9a-f]{40}) blob ([0-9]+)", line)
            if match is None or match[1].decode("ascii") != sha:
                raise AndroidError("required Android Git blob is unavailable")
            size = int(match[2])
            if size > MAX_SOURCE_BYTES:
                raise AndroidError("required Android Git source is oversized")
            self.sizes[sha] = size

    def text(self, relative):
        self.require([relative])
        sha = self.entries[relative]["sha"]
        if sha not in self.contents:
            content = self._git("cat-file", "blob", sha)
            if len(content) != self.sizes[sha]:
                raise AndroidError("Android Git source size changed")
            try:
                self.contents[sha] = content.decode("utf-8", errors="strict")
            except UnicodeError as error:
                raise AndroidError("Android Git source is not UTF-8") from error
        return self.contents[sha]

    def json(self, relative):
        try:
            return json.loads(self.text(relative), object_pairs_hook=_pairs)
        except json.JSONDecodeError as error:
            raise AndroidError("invalid Android Git JSON input") from error


def load_policy(policy_root=ROOT):
    policy = _json(_file(Path(policy_root), ".github/android-checks.json"))
    fields = {"schema", "repository", "repository_id", "branches", "environment", "reviewed_sources",
              "catalog_tiers", "catalog_suites", "executions", "views", "branch_cases",
              "robolectric_sources", "branch_robolectric_sources", "reviewed_robolectric_report"}
    if not isinstance(policy, dict) or set(policy) != fields or type(policy["schema"]) is not int \
            or policy["schema"] != 1 or policy["repository"] != "noah-l-frank/overte" \
            or policy["repository_id"] != 1319052603 or policy["environment"] != "android-host-java21-v1" \
            or set(policy["views"]) != set(VIEWS) or len(policy["branches"]) != 4 \
            or set(policy["branches"]) != {"android-main", "android-phone", "android-vr", "android-vr-pico"}:
        raise AndroidError("invalid trusted Android policy")
    for name, item in policy["executions"].items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or set(item) != {
            "command", "timeout", "variant", "report", "cases"
        } or not isinstance(item["command"], list) or len(item["command"]) < 2 \
                or item["command"][0] not in ("python", "bash") \
                or type(item["timeout"]) is not int or not 0 < item["timeout"] <= 3600 \
                or item["report"] not in (None, "native", "robolectric", "pico") \
                or not isinstance(item["cases"], list) or len(set(item["cases"])) != len(item["cases"]):
            raise AndroidError("invalid trusted Android execution declaration")
    for name, item in policy["executions"].items():
        if name == "pico4-device-free":
            continue
        original = policy["catalog_suites"].get(name)
        if original is None or item["command"] != [
            "python" if original["command"][0].endswith(".py") else "bash", *original["command"]
        ]:
            raise AndroidError("trusted Android execution disagrees with its reviewed catalog command")
    for branch, owners in policy["branch_cases"].items():
        if branch not in policy["branches"] or not isinstance(owners, dict):
            raise AndroidError("invalid Android branch assertion ownership")
        for owner, cases in owners.items():
            if owner not in policy["executions"] or not isinstance(cases, list) \
                    or len(set(cases)) != len(cases) or not set(policy["executions"][owner]["cases"]).issubset(cases):
                raise AndroidError("branch-local Android assertions omit the common inventory")
    for members in policy["views"].values():
        for proof in members.values():
            if set(proof) != {"execution", "cases"} or proof["execution"] not in policy["executions"] \
                    or not set(proof["cases"]).issubset(policy["executions"][proof["execution"]]["cases"]):
                raise AndroidError("Android view refers to an unowned assertion")
    return policy


def _validate_catalog(sources, policy):
    catalog = sources.json("android/common/tests/suite/catalog.json")
    if not isinstance(catalog, dict) or type(catalog.get("schemaVersion")) is not int or catalog.get("schemaVersion") != 1 \
            or not isinstance(catalog.get("suites"), list):
        raise AndroidError("invalid candidate Android catalog")
    observed = {}
    for entry in catalog["suites"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in observed \
                or not isinstance(entry.get("tiers"), list) or any(not isinstance(t, str) for t in entry["tiers"]) \
                or len(set(entry["tiers"])) != len(entry["tiers"]):
            raise AndroidError("duplicate or malformed candidate Android suite")
        observed[entry["id"]] = entry
    relevant = {name for name, item in observed.items() if set(item["tiers"]) & set(policy["catalog_tiers"])}
    if relevant != set(policy["catalog_suites"]):
        raise AndroidError("candidate catalog omits or adds an unreviewed mandatory Android suite")
    for name, expected in policy["catalog_suites"].items():
        actual = observed[name]
        if actual.get("command") != expected["command"] or sorted(actual["tiers"]) != expected["tiers"]:
            raise AndroidError("candidate Android suite command or tier ownership differs from trusted policy")
    sources.require(["android/" + item["command"][0] for item in policy["catalog_suites"].values()])


def _java_declarations(source):
    # Remove comments and literals before inspecting annotations. A quoted or
    # commented @Test/@Config cannot counterfeit a mandatory declaration.
    tokens = re.compile(r"""//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""", re.S)
    return tokens.sub(lambda match: " " * len(match.group()), source)


def _robolectric_cases(source_tree, branch, policy):
    sources = dict(policy["robolectric_sources"])
    sources.update(policy["branch_robolectric_sources"].get(branch, {}))
    phone = "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/"
    # The reviewed Gradle sourceSet includes every direct *RobolectricTest.java
    # in this directory. New simple classes/methods are discovered as data;
    # their omission from actual JUnit cannot hide behind the old inventory.
    for path in source_tree.entries:
        if path.startswith(phone) and "/" not in path[len(phone):] and path.endswith("RobolectricTest.java"):
            sources.setdefault(path, None)
    source_tree.require(sources)
    results = []
    for path, required in sources.items():
        source = _java_declarations(source_tree.text(path))
        package = re.search(r'\bpackage\s+([A-Za-z_][\w.]*)\s*;', source)
        name = Path(path).stem
        if package is None or not re.search(r'\bclass\s+' + re.escape(name) + r'\b', source):
            raise AndroidError("Robolectric source has an unsupported class declaration")
        qualified = package.group(1) + "." + name
        configs = re.findall(r'@Config\s*\(\s*sdk\s*=\s*\{([0-9,\s]+)\}', source)
        robolectric = name.endswith("RobolectricTest")
        if robolectric:
            if len(configs) != 1 or len(re.findall(r'@Config\b', source)) != 1 or not re.search(
                    r'@RunWith\s*\(\s*(?:org\.robolectric\.)?RobolectricTestRunner\.class\s*\)', source):
                raise AndroidError("Robolectric SDK or runner declarations require review")
            sdks = [int(value.strip()) for value in configs[0].split(",")]
            if not sdks or sorted(set(sdks)) != sdks or any(not 24 <= value <= 35 for value in sdks):
                raise AndroidError("unsupported Robolectric SDK inventory")
        else:
            sdks = []
            if configs or re.search(r'@Config\b', source):
                raise AndroidError("plain JVM fixture unexpectedly declares Android SDK variants")
        methods = re.findall(r'@Test(?:\s*\([^)]*\))?\s+public\s+void\s+([A-Za-z_]\w*)\s*\(', source)
        if not methods or len(methods) != len(set(methods)) or len(methods) != len(re.findall(r'@Test\b', source)):
            raise AndroidError("Robolectric test declarations require review")
        if required is not None and (qualified != required["class"] or sdks != required["sdks"]
                or not set(required["methods"]).issubset(methods)):
            raise AndroidError("Robolectric source omits reviewed class, SDK or method coverage")
        suffixes = [f"[{sdk}]" for sdk in sdks[:-1]] + [""]
        results.extend(qualified + "::" + method + suffix for method in methods for suffix in suffixes)
    if len(results) != len(set(results)):
        raise AndroidError("Robolectric sources have duplicated assertion identities")
    return sorted(results)


def plan(candidate, branch, *, views=None, policy_root=ROOT):
    """Plan from immutable Git objects; source files need not be checked out."""
    candidate = Path(candidate).resolve(strict=True)
    shared, _ = _shared()
    commit, tree = shared.checkout_identity(candidate)
    policy = load_policy(policy_root)
    if branch not in policy["branches"]:
        raise AndroidError("Android plan requires a reviewed product branch")
    selected = list(DEFAULT_VIEWS) if views is None else views
    if not isinstance(selected, list) or any(not isinstance(name, str) for name in selected) \
            or len(set(selected)) != len(selected) or any(name not in VIEWS for name in selected):
        raise AndroidError("Android views must be unique trusted names")
    selected = [name for name in VIEWS if name in selected]
    sources = _GitSources(candidate, commit, tree, shared)
    _validate_catalog(sources, policy)
    chosen = {name: json.loads(canonical(policy["views"][name])) for name in selected}
    names = dict.fromkeys(proof["execution"] for members in chosen.values() for proof in members.values())
    executions = {name: json.loads(canonical(policy["executions"][name])) for name in names}
    for name, cases in policy["branch_cases"].get(branch, {}).items():
        if name in executions:
            executions[name]["cases"] = cases
    if "phone-robolectric-launcher" in executions:
        executions["phone-robolectric-launcher"]["cases"] = _robolectric_cases(sources, branch, policy)
    if "pico" in chosen:
        chosen["pico"]["pico4-device-free"]["cases"] = executions["pico4-device-free"]["cases"]
    sources.require(["android/" + item["command"][1] for item in executions.values()])
    if shared.checkout_identity(candidate) != (commit, tree):
        raise AndroidError("Android checkout changed during source planning")
    source = {"policy": policy, "controller": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    result = {"schema": 1, "repository": policy["repository"], "repository_id": policy["repository_id"],
              "branch": branch, "candidate": commit, "tree": tree, "policy": digest(source),
              "environment": policy["environment"], "executions": executions, "views": chosen}
    result["plan"] = digest(result)
    return result


def _tool_identity(runtime, executable, arguments):
    path = runtime._checked_executable(executable)
    if executable == "npm":
        if path.name != "npm-cli.js":
            raise AndroidError("actual npm CLI entrypoint cannot be identified")
        output = runtime._command(runtime._checked_executable("node"), str(path), *arguments)
    else:
        output = runtime._command(path, *arguments)
    version = output.splitlines()[0]
    if len(version) > 500 or not version.isprintable():
        raise AndroidError("unsupported Android tool version metadata")
    return {"version": version, "executable_digest": runtime._file_digest(path)}


def _gcovr_identity(runtime):
    python = runtime._checked_executable(sys.executable)
    gcovr = shutil.which("gcovr")
    if gcovr is None or not Path(gcovr).is_file():
        raise AndroidError("Android coverage requires the actual gcovr executable")
    # Coverage scripts execute this entrypoint; bind its interpreter and package
    # context instead of treating an arbitrary candidate-local launcher as gcovr.
    launcher = Path(gcovr).resolve(strict=True)
    with launcher.open("rb") as source:
        shebang = source.readline(4096).decode("utf-8").strip()
    if not shebang.startswith("#!/") or Path(shebang[2:]).parent != Path(sys.executable).parent \
            or launcher.parent != Path(sys.executable).parent or Path(shebang[2:]).resolve() != python.resolve():
        raise AndroidError("gcovr must belong to the trusted execution Python environment")
    try:
        gcovr_version = importlib.metadata.version("gcovr")
    except importlib.metadata.PackageNotFoundError as error:
        raise AndroidError("required gcovr Python package is unavailable") from error
    return {"version": gcovr_version, "executable_digest": runtime._file_digest(launcher)}


def _capture_environment():
    """Capture actual tools; never accept a candidate-supplied runtime label.

    This profile does not require unrelated Qt6 development packages. Complete
    installed Debian/Python inventories bind Qt5 runtime/plugins and coverage
    tools conservatively. It is deliberately separate from shared-host reuse.
    """
    _, runtime = _shared()
    release = platform.freedesktop_os_release()
    if platform.system() != "Linux" or release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise AndroidError("unsupported actual Android host OS")
    if sys.flags.optimize or sys._xoptions:
        raise AndroidError("unsupported Android test Python interpreter flags")
    library_path = os.environ.get("LD_LIBRARY_PATH", "")
    base = Path(sys.base_prefix).resolve()
    if library_path and (library_path.split(os.pathsep) != [str(base / "lib")] or not any(
            base.is_relative_to(prefix) for prefix in (Path("/usr"), Path("/opt/hostedtoolcache")))):
        raise AndroidError("unsupported Android host runtime library search path")
    # Limit executable lookup to the reviewed hosted image and the identified JDK.
    java_home = runtime._identified_java_home()
    if java_home is None:
        raise AndroidError("Android tests require an explicitly identified Java 21 home")
    java_dirs = {str(java_home / "bin"), str(Path(os.environ["JAVA_HOME"]) / "bin")}
    for item in os.environ.get("PATH", os.defpath).split(os.pathsep):
        path = Path(item)
        if not item or not path.is_absolute() or ".." in path.parts or (
            item not in runtime._DEFAULT_PATH_DIRECTORIES and item not in java_dirs
            and not path.is_relative_to("/opt/hostedtoolcache")
            and path != Path(sys.prefix) / "bin"
        ):
            raise AndroidError("unsupported Android host executable search path")
    tools = {name: _tool_identity(runtime, command[0], command[1:]) for name, command in TOOLS.items()}
    tools["qmltestrunner"] = {"version": "Qt5", "executable_digest": runtime._file_digest(
        runtime._checked_executable("/usr/lib/qt5/bin/qmltestrunner"))}
    python = runtime._checked_executable(sys.executable)
    python_lookup = runtime._python_lookup_identity()
    gradle_home = Path(os.environ["GRADLE_USER_HOME"])
    if any((gradle_home / name).exists() for name in ("init.gradle", "init.gradle.kts")) or any(
            (gradle_home / "init.d").glob("*")):
        raise AndroidError("unsupported Gradle init scripts can change Android test selection")
    gcovr = _gcovr_identity(runtime)
    packages = runtime._command(runtime._checked_executable("dpkg-query"), "--show", "--showformat=${binary:Package}\t${Version}\t${Status}\n")
    result = {"schema": 1, "profile": "android-host-java21-v1", "system": {
        "distribution": release["ID"], "version": release["VERSION_ID"], "architecture": platform.machine(),
        "kernel": platform.release(), "packages_digest": digest(packages)},
        "tools": tools, "python": {"version": platform.python_version(), "executable_digest": runtime._file_digest(python),
        "packages": runtime._python_packages({}), "lookup": python_lookup,
        "flags": {name: getattr(sys.flags, name) for name in ("optimize", "isolated", "safe_path", "ignore_environment", "no_site")}},
        "gcovr": gcovr,
        "trusted_execution": {name: runtime._file_digest(_file(ROOT, name)) for name in EXECUTION_FILES}}
    validate_environment(result)
    return result


def validate_environment(value):
    fields = {"schema", "profile", "system", "tools", "python", "gcovr", "trusted_execution"}
    if not isinstance(value, dict) or set(value) != fields or type(value.get("schema")) is not int \
            or value["schema"] != 1 or value["profile"] != "android-host-java21-v1" \
            or not isinstance(value["tools"], dict) or set(value["tools"]) != set(TOOLS) | {"qmltestrunner"} \
            or not isinstance(value["gcovr"], dict) or value["gcovr"].get("version") != "8.4":
        raise AndroidError("Android runtime identity is incomplete or has the wrong profile")
    for name in ("java", "javac"):
        version = value["tools"][name].get("version", "")
        if not re.search(r'(?:^|[\s\"])(?:21)(?:[.\s\"]|$)', version):
            raise AndroidError("Android Robolectric ownership requires actual Java 21")
    if not re.fullmatch(r"v22(?:\.[0-9]+)+", value["tools"]["node"].get("version", "")):
        raise AndroidError("Android coverage requires actual Node 22")
    for item in [*value["tools"].values(), value["gcovr"], value["python"]]:
        if not isinstance(item, dict) or not isinstance(item.get("executable_digest"), str) \
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", item["executable_digest"]):
            raise AndroidError("Android runtime executable identity is missing")
    system, python, code = value["system"], value["python"], value["trusted_execution"]
    if not isinstance(system, dict) or system.get("distribution") != "ubuntu" or system.get("version") != "24.04" \
            or system.get("architecture") not in ("x86_64", "aarch64") or not system.get("kernel") \
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", system.get("packages_digest", "")) \
            or not isinstance(python.get("packages"), dict) or python.get("lookup") != {
                "mode": "controller-virtualenv", "aliases": ["python", "python3"],
                "include_system_site_packages": False, "user_site_enabled": False} \
            or not isinstance(python.get("flags"), dict) or python["flags"].get("optimize") != 0 \
            or not isinstance(code, dict) or set(code) != set(EXECUTION_FILES) \
            or any(not isinstance(item, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", item) for item in code.values()):
        raise AndroidError("Android runtime source, Python or system identity is missing")
    canonical(value)


@contextmanager
def process_environment(report_root):
    """Apply one policy to normalized runtime capture and candidate children."""
    shared, runtime = _shared()
    names = {name for name in os.environ if name.startswith(runtime._SENSITIVE_PREFIXES)
             and name != "LD_LIBRARY_PATH" and not name.startswith("GIT_CONFIG")}
    names |= set(runtime._UNSUPPORTED_VARIABLES)
    names |= {name for name in os.environ if name.startswith(("JAVA_TOOL_", "JDK_JAVA_", "_JAVA_", "NODE_", "GCOV_", "COVERAGE_", "GRADLE_", "ORG_GRADLE_PROJECT_"))}
    names |= {"QT_QPA_PLATFORM", "QT_QUICK_BACKEND", "TMPDIR", "MAVEN_OPTS"}
    previous = {name: os.environ.get(name) for name in names}
    fixed = {"OVERTE_REQUIRE_QML_TESTS": "1", "OVERTE_QML_TEST_RUNNER": "/usr/lib/qt5/bin/qmltestrunner",
             "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "OVERTE_ROBOLECTRIC_JAVA_HOME": os.environ.get("JAVA_HOME", ""),
             "OVERTE_TEST_REPORT_DIR": str(report_root), "OVERTE_ROBOLECTRIC_REPORT_DIR": str(report_root / "robolectric"),
             "OVERTE_GCOVR_COMMAND": "gcovr", "TMPDIR": str(report_root / "tmp"),
             "GRADLE_USER_HOME": str(Path.home() / ".gradle")}
    previous.update({name: os.environ.get(name) for name in fixed if name not in previous})
    (report_root / "tmp").mkdir(parents=True)
    with shared.candidate_process_environment():
        try:
            for name in names:
                os.environ.pop(name, None)
            fixed["OVERTE_GCOVR_COMMAND"] = shutil.which("gcovr") or "gcovr"
            os.environ.update(fixed)
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _capture_effective(capture):
    # Use the exact fixed policy used by subprocesses, including raw venv
    # invocation aliases. Temporary report paths are not part of runtime identity.
    with tempfile.TemporaryDirectory(prefix="overte-android-environment-") as directory:
        with process_environment(Path(directory)):
            return capture()


def capture_environment():
    """Observe the normalized Android child environment through trusted probes."""
    return _capture_effective(_capture_environment)


def read_cases(report_root, item):
    kind = item["report"]
    if kind is None:
        return {}, None
    paths = sorted((report_root / "robolectric").glob("TEST-*.xml")) if kind == "robolectric" else [
        report_root / ("native/TEST-native.xml" if kind == "native" else "pico.xml")]
    cases, reports = {}, {}
    if not paths:
        raise AndroidError("selected Android execution produced no fresh JUnit reports")
    for path in paths:
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(report_root)) \
                or not path.resolve().is_relative_to(report_root.resolve()) or not path.is_file() or path.stat().st_size > 20_000_000:
            raise AndroidError("selected Android execution has an unsafe or missing JUnit report")
        content = path.read_bytes()
        try:
            xml = ET.fromstring(content)
        except ET.ParseError as error:
            raise AndroidError("selected Android execution produced malformed JUnit") from error
        suites = [xml] if xml.tag == "testsuite" else list(xml.findall("testsuite")) if xml.tag == "testsuites" else []
        if not suites:
            raise AndroidError("selected Android execution produced no JUnit suites")
        for suite in suites:
            actual = list(suite.findall("testcase"))
            try:
                counts = {key: int(suite.get(key, "0")) for key in ("tests", "failures", "errors", "skipped")}
            except ValueError as error:
                raise AndroidError("invalid Android JUnit counters") from error
            if counts["tests"] != len(actual) or any(counts[key] for key in ("failures", "errors", "skipped")):
                raise AndroidError("Android JUnit is incomplete, failed or skipped")
            for case in actual:
                name = case.get("name", "")
                if kind == "robolectric":
                    if not case.get("classname"):
                        raise AndroidError("Robolectric JUnit omits its test class")
                    name = case.get("classname") + "::" + name
                if not name or name in cases or any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
                    raise AndroidError("Android JUnit contains duplicate, missing or unsuccessful cases")
                cases[name] = "passed"
        reports[path.relative_to(report_root).as_posix()] = "sha256:" + hashlib.sha256(content).hexdigest()
    if not cases or (item["cases"] and set(cases) != set(item["cases"])):
        raise AndroidError("Android JUnit omits required assertions or adds an unreviewed case inventory")
    return cases, digest(reports)


def _view_results(current_plan, results):
    views = {}
    for view, members in current_plan["views"].items():
        views[view] = {}
        for name, proof in members.items():
            result = results[proof["execution"]]
            cases = proof["cases"]
            status = "passed" if result["status"] == "passed" and all(
                result["cases"].get(case) == "passed" for case in cases) else "failed"
            views[view][name] = {"execution": proof["execution"], "status": status, "cases": cases}
    return views


def verify(candidate, branch, receipt, *, views=None, policy_root=ROOT, environment=None):
    """Recompute the required plan; a self-consistent reduced receipt cannot pass."""
    expected = plan(candidate, branch, views=views, policy_root=policy_root)
    fields = {"schema", "producer", "candidate", "tree", "branch", "policy", "plan", "environment",
              "executions", "views", "conclusion", "started_at", "completed_at", "receipt_digest"}
    if not isinstance(receipt, dict) or set(receipt) != fields or type(receipt["schema"]) is not int \
            or receipt["schema"] != 1 or receipt["producer"] != PRODUCER:
        raise AndroidError("invalid Android execution receipt")
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_digest")
    if digest(unsigned) != claimed:
        raise AndroidError("Android execution receipt digest mismatch")
    for name in ("candidate", "tree", "branch", "policy", "plan"):
        if receipt[name] != expected[name]:
            raise AndroidError("Android execution receipt source or plan mismatch")
    actual = (capture_environment() if environment is None else environment) if expected["executions"] else None
    if actual is not None:
        validate_environment(actual)
    if actual != receipt["environment"]:
        raise AndroidError("Android receipt runtime differs from the actual execution environment")
    results = receipt["executions"]
    if not isinstance(results, dict) or set(results) != set(expected["executions"]) or receipt["conclusion"] != "success":
        raise AndroidError("Android execution receipt is incomplete or unsuccessful")
    for name, item in expected["executions"].items():
        result = results[name]
        if not isinstance(result, dict) or set(result) != {"status", "returncode", "command", "cases", "reports", "environment"} \
                or result["status"] != "passed" or type(result["returncode"]) is not int or result["returncode"] != 0 \
                or result["command"] != digest(item["command"]) or result["environment"] != digest(actual) \
                or not isinstance(result["cases"], dict):
            raise AndroidError("selected Android owner did not establish successful execution")
        if item["report"] is None:
            if result["cases"] or result["reports"] is not None:
                raise AndroidError("unexpected Android assertion proof")
        elif not result["cases"] or any(status != "passed" for status in result["cases"].values()) \
                or not isinstance(result["reports"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", result["reports"]) \
                or (item["cases"] and set(result["cases"]) != set(item["cases"])):
            raise AndroidError("Android owner omits required subcase coverage")
    if receipt["views"] != _view_results(expected, results):
        raise AndroidError("Android tier view does not match observed execution owners")
    try:
        stamps = [datetime.fromisoformat(receipt[key].replace("Z", "+00:00")) for key in ("started_at", "completed_at")]
    except (TypeError, ValueError, AttributeError) as error:
        raise AndroidError("invalid Android execution timestamps") from error
    if any(stamp.utcoffset() is None for stamp in stamps) or stamps[0] > stamps[1]:
        raise AndroidError("invalid Android execution timestamp order")
    return {"verified": "true", "candidate": expected["candidate"], "tree": expected["tree"], "plan": expected["plan"]}


def execute(candidate, branch, *, views=None, policy_root=ROOT, receipt_path=None, reports=None,
            run_command=None, capture=None):
    candidate = Path(candidate).resolve(strict=True)
    current = plan(candidate, branch, views=views, policy_root=policy_root)
    # Planning and receipt verification work in a sparse metadata checkout.
    # Actual execution still requires materialized candidate entrypoints.
    for item in current["executions"].values():
        _file(candidate / "android", item["command"][1])
    if receipt_path is not None and Path(receipt_path).resolve().is_relative_to(candidate):
        raise AndroidError("Android execution receipt must be outside the immutable candidate")
    shared, _ = _shared()
    capture = _capture_environment if capture is None else capture
    environment = _capture_effective(capture) if current["executions"] else None
    if environment is not None:
        validate_environment(environment)
    controller = shared._runner()
    command_runner = controller.run_command if run_command is None else run_command
    old_root, cancelled, previous = controller.ROOT, [], {}
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    results = {}
    # Reports always start empty and remain outside the immutable source tree.
    if reports is not None:
        reports = Path(reports).resolve()
        if reports.is_relative_to(candidate) or reports.exists():
            raise AndroidError("Android report directory must be fresh and outside the candidate")
        reports.mkdir(parents=True)
    temporary = tempfile.TemporaryDirectory(prefix="overte-android-results-") if reports is None else None
    report_base = Path(temporary.name) if temporary else reports
    def interrupted(signum, _frame):
        if not cancelled:
            cancelled.append(signum)
    try:
        controller.ROOT = candidate / "android"
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        for name, item in current["executions"].items():
            report_root = report_base / name
            report_root.mkdir()
            command = [sys.executable if index == 0 and value == "python" else
                       str(report_root / "pico.xml") if value == "{report}" else value
                       for index, value in enumerate(item["command"])]
            cases, report_digest = {}, None
            with process_environment(report_root):
                returncode, _output, _message = command_runner(command, item["timeout"], cancelled)
            status = "passed" if returncode == 0 else "failed"
            if status == "passed":
                try:
                    cases, report_digest = read_cases(report_root, item)
                except (AndroidError, OSError, UnicodeError) as error:
                    status = "failed"
                    print(f"{name}: {error}", file=sys.stderr)
            results[name] = {"status": status, "returncode": returncode, "command": digest(item["command"]),
                             "cases": cases, "reports": report_digest, "environment": digest(environment)}
            print(f"{status.upper():7} {name}")
            if status == "failed" and _output:
                print(_output.rstrip(), file=sys.stderr)
    finally:
        controller.ROOT = old_root
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if temporary:
            temporary.cleanup()
    if shared.checkout_identity(candidate) != (current["candidate"], current["tree"]) or (_capture_effective(capture) if current["executions"] else None) != environment:
        raise AndroidError("Android source or runtime changed during test execution")
    view_results = _view_results(current, results)
    passed = all(result["status"] == "passed" for result in results.values())
    receipt = {"schema": 1, "producer": PRODUCER, **{key: current[key] for key in ("candidate", "tree", "branch", "policy", "plan")},
               "environment": environment, "executions": results, "views": view_results,
               "conclusion": "success" if passed else "failure", "started_at": started,
               "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    receipt["receipt_digest"] = digest(receipt)
    if receipt_path is not None:
        shared._write_receipt(receipt_path, receipt)
    return (0 if passed else 1), receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "verify"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--view", action="append", choices=VIEWS)
    selection.add_argument("--no-views", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--reports", type=Path)
    args = parser.parse_args()
    selected = [] if args.no_views else args.view
    try:
        if args.action == "plan":
            print(json.dumps(plan(args.candidate, args.branch, views=selected), sort_keys=True))
            return 0
        if args.receipt is None:
            raise AndroidError("run and verify require --receipt")
        if args.action == "run":
            return execute(args.candidate, args.branch, views=selected, receipt_path=args.receipt, reports=args.reports)[0]
        if args.receipt.resolve().is_relative_to(args.candidate.resolve()):
            raise AndroidError("verification cannot trust a candidate-supplied receipt")
        print(json.dumps(verify(args.candidate, args.branch, _json(args.receipt), views=selected), sort_keys=True))
        return 0
    except (AndroidError, ValueError, OSError) as error:
        print(f"Android validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
