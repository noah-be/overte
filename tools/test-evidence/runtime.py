#!/usr/bin/env python3
"""Capture the actual portable-host test environment without inspecting secrets.

This intentionally conservative common profile binds the complete installed
Debian/Python package inventories. Future reviewed suite-specific profiles can
narrow that identity. Unknown overrides never become matching unknown values.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
import hashlib
import json
import os
import platform
import re
import shutil
import site
import subprocess
import sys
import sysconfig


class RuntimeIdentityError(ValueError):
    """The actual host environment cannot authorize reusable evidence."""


ROOT = Path(__file__).resolve().parents[2]
_TIMEOUT_SECONDS = 10
_MAX_OUTPUT_BYTES = 2_000_000
_TOOL_ROOTS = (Path("/usr/bin"), Path("/usr/lib"), Path("/usr/local/bin"), Path("/opt/hostedtoolcache"))
_DEFAULT_PATH_DIRECTORIES = {
    "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin",
    "/usr/local/.ghcup/bin", "/opt/pipx_bin", "/snap/bin", "/home/runner/.cargo/bin",
    "/home/runner/.dotnet/tools", "/home/runner/.local/share/powershell", "/home/runner/.local/bin",
    "/home/linuxbrew/.linuxbrew/bin", "/home/linuxbrew/.linuxbrew/sbin",
    "/usr/local/games", "/usr/games", "/home/runner/.ghcup/bin",
    # Official Ubuntu image install-php.sh adds this exact Composer directory.
    # https://github.com/actions/runner-images/blob/ubuntu24/20261012.334/images/ubuntu/scripts/build/install-php.sh#L96
    "/home/runner/.config/composer/vendor/bin",
}
_COMMANDS = {
    "bash": ("bash", "--version"),
    "cmake": ("cmake", "--version"),
    "compiler": ("c++", "--version"),
    "ctest": ("ctest", "--version"),
    "git": ("git", "--version"),
    "java": ("java", "--version"),
    "javac": ("javac", "--version"),
    "jq": ("jq", "--version"),
    "ninja": ("ninja", "--version"),
    "node": ("node", "--version"),
    "npm": ("npm", "--version"),
    "pkg-config": ("pkg-config", "--version"),
    "unshare": ("unshare", "--version"),
}
_QT_MODULES = tuple(f"Qt{major}{component}" for major in (5, 6)
                    for component in ("Core", "Gui", "Quick", "Qml", "WebChannel", "Network", "Concurrent"))
_CHOICES = {
    "OVERTE_CREDENTIAL_QT_MAJOR": (("5", "6"), "6"),
    "OVERTE_GOTO_TEST_QT": (("Qt5", "Qt6"), "Qt6"),
    "OVERTE_LOGIN_TEST_QT": (("Qt5", "Qt6"), "Qt6"),
    "OVERTE_NATIVE_QT_MAJOR": (("5", "6"), "5"),
    "OVERTE_SNAPSHOT_TEST_QT": (("Qt5", "Qt6"), "Qt6"),
    "OVERTE_VOICE_TEST_QT_CORE": (("Qt5Core", "Qt6Core"), "Qt6Core"),
    "OVERTE_WEB_VISIBILITY_QT": (("Qt5", "Qt6"), "Qt6"),
    "SAFE_LANDING_QT_CORE": (("Qt5Core", "Qt6Core"), "Qt6Core"),
    "QT_QPA_PLATFORM": (("offscreen",), "offscreen"),
    "QT_QUICK_BACKEND": (("software",), "software"),
}
_SENSITIVE_PREFIXES = (
    "OVERTE_", "SAFE_LANDING_", "V8_", "QT", "QSG_", "QML", "PKG_CONFIG_", "CMAKE_", "CONAN_",
    "PYTHON", "NODE_", "NPM_CONFIG_", "npm_config_", "JAVA_TOOL_", "JDK_JAVA_", "_JAVA_", "LD_", "DYLD_",
    "ASAN_", "TSAN_", "LSAN_", "UBSAN_", "MSAN_", "GCOV_", "LLVM_PROFILE_", "COVERAGE_",
    "GIT_CONFIG", "LIBGL_", "MESA_", "GALLIUM_", "EGL_", "OMP_",
)
_UNSUPPORTED_VARIABLES = {
    "CC", "CXX", "CPP", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CPATH", "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "GCC_EXEC_PREFIX", "COMPILER_PATH", "BASH_ENV", "ENV",
    "CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR", "CLASSPATH", "JAVA_OPTS", "JAVAC_OPTS",
}
_TRUSTED_EXECUTION_FILES = (
    "tools/test-evidence/run.py", "tools/test-evidence/execution.py", "tools/test-evidence/inputs.py",
    "tools/test-evidence/runtime.py", "tests/run-project-tests.py", "tools/sync-test-reuse/qualification.py",
    "tools/test-evidence/attested.py", ".github/attested-runtime.json",
    "tools/test-evidence/sandbox_host.py", "tools/test-evidence/sandbox_shared.py",
    "tools/test-evidence/producer_workflow.py",
)
_FIXED_GIT_OVERRIDES = {
    "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0",
}
_PYTHON_LOOKUP_PROBE = (
    "import json,site,sys;print(json.dumps({'prefix':sys.prefix,"
    "'base_prefix':sys.base_prefix,'user_site':site.ENABLE_USER_SITE}))"
)


def _fail(label: str) -> RuntimeIdentityError:
    # Never interpolate command output, environment names/values, private paths,
    # exception strings, or target selectors into errors surfaced by workflows.
    return RuntimeIdentityError(label)


def _checked_executable(value: str) -> Path:
    try:
        located = shutil.which(value)
        if located is None:
            raise _fail("a required host tool is unavailable")
        path = Path(located).resolve(strict=True)
        if not path.is_file() or not any(path.is_relative_to(root) for root in _TOOL_ROOTS):
            raise _fail("a host tool resolves outside the supported system installation")
        return path
    except OSError as error:
        raise _fail("a required host tool cannot be identified") from error


def _required_tool(name: str) -> Path:
    """Expose only a fixed public tool role, never a discovered path or output."""
    if type(name) is not str or name not in _COMMANDS:
        raise _fail("unsupported required host tool role")
    try:
        return _checked_executable(_COMMANDS[name][0])
    except RuntimeIdentityError:
        raise _fail("a required host tool cannot be identified: " + name) from None


def _file_digest(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    except OSError as error:
        raise _fail("a required runtime input cannot be read") from error


def _command(executable: Path, *arguments: str, python_environment: bool = False) -> str:
    # Only fixed read-only queries call this helper. Running from / and using a
    # small environment prevents tool discovery/imports from the candidate tree.
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": "/nonexistent"}
    if python_environment:
        # setup-python's shared interpreter can require its own already bound
        # base library directory. No arbitrary inherited overlay is forwarded.
        environment["LD_LIBRARY_PATH"] = str(Path(sys.base_prefix).resolve() / "lib")
    try:
        result = subprocess.run(
            [str(executable), *arguments], cwd="/", check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=_TIMEOUT_SECONDS,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise _fail("a required read-only runtime identity query failed") from error
    if len(result.stdout.encode("utf-8")) > _MAX_OUTPUT_BYTES or not result.stdout.strip():
        raise _fail("a runtime identity query returned unavailable or unsupported data")
    return result.stdout.strip()


def _identified_java_home() -> Path | None:
    value = os.environ.get("JAVA_HOME")
    if not value:
        return None
    original = Path(value)
    if not original.is_absolute() or ".." in original.parts or not any(original.is_relative_to(root) for root in (
        Path("/usr/lib/jvm"), Path("/opt/hostedtoolcache"),
    )):
        raise _fail("the Java installation override is outside supported system installations")
    try:
        home = original.resolve(strict=True)
        if (home / "bin/java").resolve(strict=True) != _checked_executable("java") \
                or (home / "bin/javac").resolve(strict=True) != _checked_executable("javac"):
            raise _fail("the Java installation override differs from identified host tools")
    except OSError as error:
        raise _fail("the Java installation override cannot be identified") from error
    return home


def _python_lookup_identity() -> dict:
    """Prove env-python aliases use the controller's effective Python prefix."""
    executable = Path(sys.executable)
    directory = executable.parent
    if not executable.is_absolute():
        raise _fail("the controller Python invocation path is unsupported")
    virtual = sys.prefix != sys.base_prefix
    if virtual:
        if os.environ.get("VIRTUAL_ENV") != sys.prefix:
            raise _fail("the Python virtualenv process environment is not normalized")
        try:
            config = {}
            for line in (Path(sys.prefix) / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        except (OSError, UnicodeError) as error:
            raise _fail("the actual Python virtualenv configuration is unavailable") from error
        if config.get("include-system-site-packages", "").lower() != "false":
            raise _fail("the Python virtualenv must exclude unbound base site packages")
    elif "VIRTUAL_ENV" in os.environ:
        raise _fail("the Python process environment claims another virtualenv")
    if site.ENABLE_USER_SITE is not False:
        raise _fail("the controller Python environment must exclude unbound user site packages")
    try:
        resolved = executable.resolve(strict=True)
        for name in ("python", "python3"):
            located = shutil.which(name)
            if located is None or Path(located).parent != directory \
                    or Path(located).resolve(strict=True) != resolved:
                raise _fail("ambient Python aliases do not use the identified controller environment")
            observed = json.loads(_command(Path(located), "-B", "-c", _PYTHON_LOOKUP_PROBE, python_environment=True))
            if observed != {"prefix": sys.prefix, "base_prefix": sys.base_prefix, "user_site": False}:
                raise _fail("ambient Python aliases have a different effective package environment")
    except OSError as error:
        raise _fail("the effective child Python environment cannot be identified") from error
    except (ValueError, TypeError) as error:
        raise _fail("the effective child Python environment returned unsupported identity data") from error
    return {"mode": "controller-virtualenv" if virtual else "controller-base", "aliases": ["python", "python3"],
            "include_system_site_packages": False if virtual else None, "user_site_enabled": False}


def _flags() -> dict[str, str]:
    if sys._xoptions:
        raise _fail("unsupported Python interpreter options prevent reusable evidence")
    git_names = {name for name in os.environ if name.startswith("GIT_CONFIG")}
    # The manual shared-host diagnostic has immutable root-owned source at
    # exactly /work. Bind its one safe-directory exception distinctly; retain
    # the ordinary two-setting profile and reject wildcard/ambient additions.
    safe_work = {**_FIXED_GIT_OVERRIDES, "GIT_CONFIG_COUNT": "3",
                 "GIT_CONFIG_KEY_2": "safe.directory", "GIT_CONFIG_VALUE_2": "/work"}
    git_profile = next((label for values, label in (
        (_FIXED_GIT_OVERRIDES, "maintenance-disabled"),
        (safe_work, "maintenance-disabled-safe-work"),
    ) if git_names == set(values) and all(os.environ[name] == value for name, value in values.items())), None)
    if git_names and git_profile is None:
        raise _fail("unsupported Git process overrides prevent reusable evidence")
    allowed = set(_CHOICES) | {"OVERTE_QML_TEST_RUNNER", "PKG_CONFIG_PATH", "LD_LIBRARY_PATH"} | set(safe_work)
    for name in os.environ:
        if name not in allowed and (
            name in _UNSUPPORTED_VARIABLES or name.startswith(_SENSITIVE_PREFIXES)
        ):
            raise _fail("unsupported host test environment overrides prevent reusable evidence")
    java_home = _identified_java_home()
    java_directories = {str(java_home / "bin"), str(Path(os.environ["JAVA_HOME"]) / "bin")} if java_home else set()
    python_directory = str(Path(sys.executable).parent)
    for directory in os.environ.get("PATH", os.defpath).split(os.pathsep):
        path = Path(directory)
        if not directory or not path.is_absolute() or ".." in path.parts or (
            directory not in _DEFAULT_PATH_DIRECTORIES and directory not in java_directories and directory != python_directory
            and not path.is_relative_to("/opt/hostedtoolcache")
        ):
            raise _fail("unsupported host executable search paths prevent reusable evidence")
    flags = {}
    flags["git_process_overrides"] = git_profile if git_names else "none"
    flags["JAVA_HOME"] = "identified-jdk" if java_home else "path"
    for name, (choices, default) in _CHOICES.items():
        value = os.environ.get(name, default)
        if value not in choices:
            raise _fail("unsupported host test environment overrides prevent reusable evidence")
        flags[name] = value
    qml_runner = os.environ.get("OVERTE_QML_TEST_RUNNER")
    if qml_runner not in ("/usr/lib/qt5/bin/qmltestrunner", "/usr/lib/qt6/bin/qmltestrunner"):
        raise _fail("the actual QML test runner must be explicitly identified")
    flags["OVERTE_QML_TEST_RUNNER"] = "Qt5" if "/qt5/" in qml_runner else "Qt6"
    # actions/setup-python exports these two paths. They are supported only for
    # the actual trusted base interpreter, whose binary/library identities are
    # captured independently. Custom sysroots or library overlays are rejected.
    base = Path(sys.base_prefix).resolve()
    for name, suffix, marker in (
        ("PKG_CONFIG_PATH", "lib/pkgconfig", "python-base-pkgconfig"),
        ("LD_LIBRARY_PATH", "lib", "python-base-lib"),
    ):
        values = os.environ.get(name, "")
        if values:
            expected = str(base / suffix)
            if values.split(os.pathsep) != [expected] or not any(base.is_relative_to(root) for root in (
                Path("/usr"), Path("/opt/hostedtoolcache"),
            )):
                raise _fail("unsupported host runtime search paths prevent reusable evidence")
            flags[name] = marker
        else:
            flags[name] = "system"
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "TZ"):
        value = os.environ.get(name, "")
        if value and not re.fullmatch(r"[A-Za-z0-9_.+/@:-]{1,100}", value):
            raise _fail("unsupported locale or timezone prevents reusable evidence")
        flags[name] = value
    return flags


def _requirement_inventory(root: Path = ROOT) -> tuple[dict[str, str], dict[str, str]]:
    """Read only the trusted, bounded, pinned host requirement manifests."""
    root = root.resolve()
    requirements = {}
    manifests = {}
    visited = set()

    def read(relative: Path) -> None:
        try:
            path = (root / relative).resolve(strict=True)
            if not path.is_relative_to(root) or path in visited:
                if path in visited:
                    return
                raise _fail("host requirements escape the trusted checkout")
            visited.add(path)
            if len(visited) > 20 or path.stat().st_size > 100_000:
                raise _fail("host requirement manifest is unsupported")
            content = path.read_bytes()
            source = content.decode("utf-8")
            manifests[path.relative_to(root).as_posix()] = "sha256:" + hashlib.sha256(content).hexdigest()
        except (OSError, UnicodeError) as error:
            raise _fail("trusted host requirement manifests are unavailable") from error
        for line in source.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("-r "):
                read(path.parent.relative_to(root) / line[3:].strip())
                continue
            match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)", line)
            if not match:
                raise _fail("host requirements must use supported exact version pins")
            name = re.sub(r"[-_.]+", "-", match[1]).lower()
            if name in requirements and requirements[name] != match[2]:
                raise _fail("trusted host requirements contain conflicting version pins")
            requirements[name] = match[2]

    read(Path("tests/requirements-host.txt"))
    if not requirements:
        raise _fail("trusted host requirement inventory is empty")
    return dict(sorted(requirements.items())), dict(sorted(manifests.items()))


def _requirements(root: Path = ROOT) -> dict[str, str]:
    return _requirement_inventory(root)[0]


def _controller_file_hashes(manifests: dict[str, str], root: Path = ROOT) -> dict[str, str]:
    """Bind the actual default-branch controller/attestor, not candidate copies.

    The complete registry is deliberately excluded: each suite fingerprint
    already binds its trusted definition, so an unrelated definition change
    need not invalidate every other reviewed suite.
    """
    root = root.resolve()
    identities = dict(manifests)
    for relative in _TRUSTED_EXECUTION_FILES:
        path = root / relative
        current = root
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise _fail("trusted execution identity contains an unsupported symbolic link")
        try:
            if not path.resolve(strict=True).is_relative_to(root):
                raise _fail("trusted execution identity escapes its reviewed checkout")
        except OSError as error:
            raise _fail("actual trusted execution files are unavailable") from error
        identities[relative] = _file_digest(path)
    return dict(sorted(identities.items()))


def _python_packages(required: dict[str, str]) -> dict[str, str]:
    try:
        paths = sysconfig.get_paths()
        locations = sorted({paths["purelib"], paths["platlib"]})
        packages = {}
        for distribution in metadata.distributions(path=locations):
            name = distribution.metadata.get("Name", "")
            version = distribution.version
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) \
                    or not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]*", version):
                raise _fail("installed Python dependency identity is unsupported")
            name = re.sub(r"[-_.]+", "-", name).lower()
            if name in packages:
                raise _fail("installed Python dependency identity is ambiguous")
            packages[name] = version
    except (OSError, KeyError, UnicodeError) as error:
        raise _fail("installed Python dependency identity is unavailable") from error
    if any(packages.get(name) != version for name, version in required.items()):
        raise _fail("required host Python dependencies are missing or differ from trusted pins")
    return dict(sorted(packages.items()))


def _debian_packages() -> dict[str, str]:
    command = _checked_executable("dpkg-query")
    source = _command(command, "--show", "--showformat=${binary:Package}\t${Version}\t${Status}\n")
    packages = {}
    for line in source.splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            raise _fail("installed system package identity is unsupported")
        name, version, status = fields
        if status != "install ok installed":
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?", name) \
                or not re.fullmatch(r"[A-Za-z0-9.+:~_-]+", version) or name in packages:
            raise _fail("installed system package identity is ambiguous or unsupported")
        packages[name] = version
    if not any(name.split(":", 1)[0] == "libglm-dev" for name in packages):
        raise _fail("the required host GLM dependency is unavailable")
    return dict(sorted(packages.items()))


def _os_identity() -> dict:
    try:
        release = platform.freedesktop_os_release()
    except OSError as error:
        raise _fail("the actual host OS identity is unavailable") from error
    if platform.system() != "Linux" or release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise _fail("the actual host OS is outside the supported portable test profile")
    architecture = platform.machine()
    if architecture not in ("x86_64", "aarch64"):
        raise _fail("the actual host architecture is unsupported")
    runner = {name: os.environ.get(name, "") for name in ("ImageOS", "ImageVersion", "RUNNER_ENVIRONMENT")}
    if runner["RUNNER_ENVIRONMENT"] != "github-hosted" \
            or not re.fullmatch(r"ubuntu[0-9]+", runner["ImageOS"]) \
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", runner["ImageVersion"]):
        raise _fail("the trusted GitHub-hosted runner image identity is unavailable")
    namespace = {}
    for name, path in {
        "apparmor_restrict_unprivileged_userns": "/proc/sys/kernel/apparmor_restrict_unprivileged_userns",
        "max_user_namespaces": "/proc/sys/user/max_user_namespaces",
    }.items():
        try:
            value = Path(path).read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise _fail("the actual host isolation configuration is unavailable") from error
        if not value.isascii() or not value.isdigit():
            raise _fail("the actual host isolation configuration is unsupported")
        namespace[name] = value
    return {"distribution": release["ID"], "version": release["VERSION_ID"], "architecture": architecture,
            "kernel": platform.release(), "runner": runner, "namespace": namespace,
            "timezone_digest": _file_digest(Path("/etc/localtime"))}


def capture_host_environment() -> dict:
    """Return complete supported runtime identity, or raise RuntimeIdentityError.

    Invoke with the same prepared host-tests virtualenv Python used by suites,
    after all prerequisite/isolation setup. Only fixed system queries execute;
    no candidate files, network request, build, or sudo operation is involved.
    """
    flags = _flags()
    python_lookup = _python_lookup_identity()
    operating_system = _os_identity()
    python = _checked_executable(sys.executable)
    if platform.python_implementation() != "CPython":
        raise _fail("the actual Python implementation is unsupported")
    library_directory = sysconfig.get_config_var("LIBDIR")
    library_name = sysconfig.get_config_var("LDLIBRARY")
    if not isinstance(library_directory, str) or not isinstance(library_name, str) or "/" in library_name:
        raise _fail("the actual Python runtime library is unavailable")
    python_library = _checked_executable(str(Path(library_directory) / library_name))
    tools = {}
    resolved_tools = {}
    for name, (executable, *arguments) in _COMMANDS.items():
        path = _required_tool(name)
        if name == "npm":
            # npm is a JavaScript entrypoint with an /usr/bin/env node shebang.
            # The sanitized query PATH must not replace setup-node's identified
            # interpreter with an absent or unrelated /usr/bin/node.
            if path.name != "npm-cli.js" or "node" not in resolved_tools:
                raise _fail("the actual npm CLI entrypoint cannot be identified")
            output = _command(resolved_tools["node"], str(path), *arguments)
        else:
            output = _command(path, *arguments)
        # Version first lines contain public identities; binary digests bind
        # the actual resolved executable without embedding checkout/home paths.
        version = output.splitlines()[0]
        if len(version) > 500 or not re.fullmatch(r"[A-Za-z0-9 ._+():,/'\";=\[\]~@-]+", version):
            raise _fail("a required host tool returned unsupported version metadata")
        tools[name] = {"version": version, "executable_digest": _file_digest(path)}
        resolved_tools[name] = path
    pkg_config = _checked_executable("pkg-config")
    qt = {module: _command(pkg_config, "--modversion", module) for module in _QT_MODULES}
    if any(not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:[-+][A-Za-z0-9_.-]+)?", version) for version in qt.values()):
        raise _fail("the actual Qt dependency version identity is unsupported")
    qt_tools = {}
    for major in (5, 6):
        directory = "/usr/lib/qt5/bin" if major == 5 else "/usr/lib/qt6/libexec"
        moc = _checked_executable(directory + "/moc")
        qt_tools[f"Qt{major}-moc"] = _file_digest(moc)
    runner = _checked_executable(os.environ["OVERTE_QML_TEST_RUNNER"])
    qt_tools["qmltestrunner"] = _file_digest(runner)
    # A user-local Qt installation is chosen ahead of pkg-config by some host
    # harnesses. It requires a separate identity profile and cannot be ignored.
    if (Path.home() / ".local/overte-qt5/root/usr/lib64/pkgconfig/Qt5Core.pc").exists():
        raise _fail("an unsupported local Qt installation prevents reusable evidence")
    required, manifests = _requirement_inventory()
    identity = {
        "schema": 1,
        "profile": "ubuntu24-host-qt5-qt6-v1",
        "os": operating_system,
        "python": {"implementation": platform.python_implementation(), "version": platform.python_version(),
                   "executable_digest": _file_digest(python), "library_digest": _file_digest(python_library),
                   "flags": {name: getattr(sys.flags, name) for name in (
                       "debug", "inspect", "interactive", "optimize", "dont_write_bytecode", "no_user_site",
                       "no_site", "ignore_environment", "verbose", "bytes_warning", "quiet", "hash_randomization",
                       "isolated", "dev_mode", "utf8_mode", "warn_default_encoding", "safe_path",
                   )}, "packages": _python_packages(required), "process_lookup": python_lookup},
        "tools": tools,
        "qt": {"modules": qt, "tools": qt_tools},
        "glm": {"header_digest": _file_digest(Path("/usr/include/glm/glm.hpp")),
                "configuration_digest": _file_digest(Path("/usr/include/glm/detail/setup.hpp"))},
        "system_packages": _debian_packages(),
        "flags": flags,
        "trusted_execution": _controller_file_hashes(manifests),
    }
    # Make the contract explicitly JSON-only and independent of insertion order.
    return json.loads(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False))


def capture_isolated_host_environment(prepared: dict) -> dict:
    """Capture full E inside the protected namespace after readonly mount proof.

    ``prepared`` comes from the root-owned projected binding, measured before
    execution and independently rehashed after cleanup. Its authenticated
    readonly mounts avoid a redundant full installation reread in each probe.
    Callers outside that protected protocol gain no evidence authority here.
    """
    # The tiny boundary-only projection deliberately has no inputs.py. Only
    # the full protected policy projection enters this capture implementation.
    import inputs

    identity = capture_host_environment()
    try:
        python = Path(sys.base_prefix).resolve(strict=True)
        node = _checked_executable("node").parent.parent
        java = _identified_java_home()
        expected_python = Path("/opt/hostedtoolcache/Python") / identity["python"]["version"] / "x64"
        expected_node = Path("/opt/hostedtoolcache/node") / identity["tools"]["node"]["version"].removeprefix("v") / "x64"
        if Path(sys.prefix) != Path(inputs.ISOLATED_VENV) or python != expected_python or node != expected_node \
                or java != Path(inputs.ISOLATED_JDK) \
                or _checked_executable("node") != node / "bin/node":
            raise _fail("isolated prepared roots differ from actual runtime tools")
        alias = java / "lib/security/cacerts"
        external = [inputs.ISOLATED_CACERTS] if alias.is_symlink() \
            and os.readlink(alias) == inputs.ISOLATED_CACERTS else []
        if external and alias.resolve(strict=True) != Path(inputs.ISOLATED_CACERTS):
            raise _fail("isolated prepared certificate alias differs from its bound input")
        identity.update(schema=inputs.ISOLATED_FULL_SCHEMA, profile=inputs.ISOLATED_FULL_PROFILE,
                        prepared={"schema": 1, "roots": prepared, "external_inputs": external})
        inputs._environment(identity)
    except (OSError, RuntimeError, inputs.InputError, KeyError, TypeError) as error:
        raise _fail("isolated prepared runtime identity is incomplete") from error
    # Do not retain a mutable alias to the projected binding or caller's map.
    return json.loads(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False))
