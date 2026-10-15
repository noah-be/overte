#!/usr/bin/env python3
"""Offline runtime-identity tests; no host queries, installs or builds."""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import json
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("test_evidence_runtime", Path(__file__).with_name("runtime.py"))
RUNTIME = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(RUNTIME)

_BASE_ENVIRONMENT = {
    "OVERTE_QML_TEST_RUNNER": "/usr/lib/qt6/bin/qmltestrunner",
    "ImageOS": "ubuntu24", "ImageVersion": "20261001.1.0", "RUNNER_ENVIRONMENT": "github-hosted",
}


class RuntimeIdentityTests(unittest.TestCase):
    def capture(self, environment=None, versions=None, queries=None):
        versions = versions or {}

        def query(executable, *arguments):
            if queries is not None:
                queries.append((executable, arguments))
            if "--modversion" in arguments:
                return versions.get(arguments[-1], "5.15.13" if arguments[-1].startswith("Qt5") else "6.4.2")
            if arguments and arguments[0].endswith("/npm-cli.js"):
                return versions.get("npm", "10.9.2")
            return versions.get(executable.name, {"java": "openjdk 17.0.18 2026-01-20",
                               "node": "v22.16.0", "c++": "c++ (Ubuntu 13.3.0) 13.3.0"}.get(executable.name, "tool 1.0.0"))

        def tool(value):
            if value == "node":
                return Path("/opt/hostedtoolcache/node/22/x64/bin/node")
            if value == "npm":
                return Path("/opt/hostedtoolcache/node/22/x64/lib/node_modules/npm/bin/npm-cli.js")
            return Path("/usr/bin") / Path(value).name

        with ExitStack() as stack:
            stack.enter_context(patch.dict(RUNTIME.os.environ, _BASE_ENVIRONMENT | (environment or {}), clear=True))
            stack.enter_context(patch.object(RUNTIME, "_os_identity", return_value={"distribution": "ubuntu", "version": "24.04"}))
            stack.enter_context(patch.object(RUNTIME, "_checked_executable", side_effect=tool))
            stack.enter_context(patch.object(RUNTIME, "_file_digest", side_effect=lambda path: "sha256:" + ("b" if path.name in versions else "a") * 64))
            stack.enter_context(patch.object(RUNTIME, "_command", side_effect=query))
            stack.enter_context(patch.object(RUNTIME, "_requirement_inventory", return_value=(
                {"pyyaml": "6.0.3"}, {"tests/requirements-host.txt": "sha256:" + "a" * 64})))
            stack.enter_context(patch.object(RUNTIME, "_python_packages", return_value={"pyyaml": "6.0.3", "pillow": "12.3.0"}))
            stack.enter_context(patch.object(RUNTIME, "_debian_packages", return_value={"libglm-dev": "1.0.1"}))
            stack.enter_context(patch.object(RUNTIME.Path, "home", return_value=Path("/nonexistent-host-home")))
            stack.enter_context(patch.object(RUNTIME.platform, "python_implementation", return_value="CPython"))
            stack.enter_context(patch.object(RUNTIME.platform, "python_version", return_value="3.12.12"))
            stack.enter_context(patch.object(RUNTIME.sysconfig, "get_config_var", side_effect=lambda name: {
                "LIBDIR": "/usr/lib", "LDLIBRARY": "libpython3.12.so",
            }.get(name)))
            return RUNTIME.capture_host_environment()

    def test_capture_is_deterministic_json_and_omits_private_environment(self):
        identity = self.capture({"GH_TOKEN": "private-token", "DEVICE_SERIAL": "private-device", "HOME": "/private/home"})
        self.assertEqual(identity, self.capture())
        self.assertEqual(identity, json.loads(json.dumps(identity)))
        serialized = json.dumps(identity)
        self.assertNotIn("private-token", serialized)
        self.assertNotIn("private-device", serialized)
        self.assertNotIn("private/home", serialized)
        self.assertEqual(identity["flags"]["OVERTE_QML_TEST_RUNNER"], "Qt6")
        self.assertNotIn("executable", identity["python"])

    def test_actual_toolchain_qt_and_backend_changes_are_visible(self):
        original = self.capture()
        self.assertNotEqual(original, self.capture(versions={"node": "v22.17.0"}))
        self.assertNotEqual(original, self.capture(versions={"Qt6Core": "6.5.0"}))
        self.assertNotEqual(original, self.capture({"OVERTE_NATIVE_QT_MAJOR": "6"}))

    def test_npm_probe_uses_identified_setup_node_interpreter_outside_system_path(self):
        queries = []
        identity = self.capture(queries=queries)
        npm_queries = [(executable, arguments) for executable, arguments in queries
                       if arguments and arguments[0].endswith("/npm-cli.js")]
        self.assertEqual(npm_queries, [(Path("/opt/hostedtoolcache/node/22/x64/bin/node"), (
            "/opt/hostedtoolcache/node/22/x64/lib/node_modules/npm/bin/npm-cli.js", "--version"))])
        self.assertEqual(identity["tools"]["npm"]["version"], "10.9.2")

    def test_supported_explicit_default_overrides_normalize(self):
        self.assertEqual(self.capture(), self.capture({"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"}))

    def test_unknown_override_and_test_mutation_cannot_produce_matching_unknown(self):
        for variable in ("OVERTE_NEW_TEST_FLAG", "OVERTE_TEST_GLM_INCLUDE", "OVERTE_QT5_ROOT",
                         "OVERTE_WEB_VISIBILITY_BASELINE", "OVERTE_DEVICE_TARGET_SELECTOR",
                         "SAFE_LANDING_BASELINE", "V8_TEST_ROOT", "CXX", "LD_PRELOAD", "PYTHONPATH",
                         "NODE_OPTIONS", "JAVA_TOOL_OPTIONS", "PKG_CONFIG_SYSROOT_DIR", "QT_PLUGIN_PATH",
                         "QSG_RHI_BACKEND", "NPM_CONFIG_USERCONFIG", "CLASSPATH"):
            with self.subTest(variable=variable), self.assertRaises(RUNTIME.RuntimeIdentityError) as raised:
                self.capture({variable: "private-override-value"})
            self.assertNotIn("private-override-value", str(raised.exception))
            self.assertNotIn(variable, str(raised.exception))
        with self.assertRaises(RUNTIME.RuntimeIdentityError):
            self.capture({"OVERTE_NEW_TEST_FLAG": ""})

    def test_search_paths_reject_candidate_tools_and_allow_only_setup_python_overlays(self):
        for search in (".:/usr/bin", "/candidate/bin:/usr/bin", "relative/bin:/usr/bin", "/usr/bin:"):
            with self.subTest(search=search), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture({"PATH": search})
        base = Path(RUNTIME.sys.base_prefix).resolve()
        self.capture({"PATH": "/opt/hostedtoolcache/node/22/x64/bin:/usr/bin:/bin",
                      "PKG_CONFIG_PATH": str(base / "lib/pkgconfig"), "LD_LIBRARY_PATH": str(base / "lib")})
        with self.assertRaises(RUNTIME.RuntimeIdentityError):
            self.capture({"LD_LIBRARY_PATH": "/candidate/lib"})

    def test_standard_hosted_path_allows_only_the_identified_system_jdk_directory(self):
        java_home = Path("/usr/lib/jvm/temurin-17-jdk-amd64")
        standard_path = ":".join((
            "/opt/hostedtoolcache/Python/3.12.12/x64/bin", "/opt/hostedtoolcache/node/22/x64/bin",
            str(java_home / "bin"), "/home/runner/.cargo/bin", "/home/linuxbrew/.linuxbrew/bin",
            "/home/linuxbrew/.linuxbrew/sbin", "/home/runner/.ghcup/bin", "/usr/local/.ghcup/bin",
            "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin",
            "/usr/local/games", "/usr/games", "/home/runner/.dotnet/tools",
            "/home/runner/.local/share/powershell", "/home/runner/.local/bin", "/opt/pipx_bin", "/snap/bin",
        ))
        with patch.dict(RUNTIME.os.environ, _BASE_ENVIRONMENT | {"JAVA_HOME": str(java_home), "PATH": standard_path}, clear=True), \
                patch.object(RUNTIME.Path, "resolve", autospec=True, side_effect=lambda path, *args, **kwargs: path), \
                patch.object(RUNTIME, "_checked_executable", side_effect=lambda value: java_home / "bin" / value):
            self.assertEqual(RUNTIME._flags()["JAVA_HOME"], "identified-jdk")
            with patch.dict(RUNTIME.os.environ, {"PATH": standard_path + ":/usr/lib/jvm/unidentified-jdk/bin"}), \
                    self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._flags()
            with patch.dict(RUNTIME.os.environ, {"JAVA_HOME": "/candidate/jdk", "PATH": "/candidate/jdk/bin:/usr/bin"}), \
                    self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._flags()
            with patch.object(RUNTIME, "_checked_executable", return_value=Path("/usr/bin/unrelated-java")), \
                    self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._flags()

    def test_custom_or_unidentified_qml_runner_is_not_executed(self):
        for runner in ("", "/candidate/runner", "qmltestrunner"):
            with self.subTest(runner=runner), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture({"OVERTE_QML_TEST_RUNNER": runner})

    def test_unsupported_backend_fails_closed(self):
        for environment in ({"QT_QPA_PLATFORM": "xcb"}, {"QT_QUICK_BACKEND": "opengl"},
                            {"OVERTE_NATIVE_QT_MAJOR": "unknown"}):
            with self.subTest(environment=environment), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture(environment)
        with self.assertRaises(RUNTIME.RuntimeIdentityError):
            self.capture({"JAVA_HOME": "/candidate/custom-jdk"})
        with patch.object(RUNTIME.sys, "_xoptions", {"tracemalloc": "private-value"}), self.assertRaises(RUNTIME.RuntimeIdentityError):
            self.capture()

    def test_missing_prerequisite_cannot_produce_partial_identity(self):
        with patch.object(RUNTIME, "_python_packages", side_effect=RUNTIME.RuntimeIdentityError("missing")):
            # Exercise missing tools directly: capture helper mocks package data.
            with patch.object(RUNTIME.shutil, "which", return_value=None), self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._checked_executable("node")
        with patch.object(RUNTIME.shutil, "which", return_value="/candidate/fake-node"), \
                patch.object(RUNTIME.Path, "resolve", return_value=Path("/candidate/fake-node")), \
                patch.object(RUNTIME.Path, "is_file", return_value=True), self.assertRaises(RUNTIME.RuntimeIdentityError):
            RUNTIME._checked_executable("node")

    def test_queries_are_bounded_fixed_read_only_and_strip_secrets(self):
        with patch.object(RUNTIME.subprocess, "run", return_value=SimpleNamespace(stdout="v22.16.0\n")) as query:
            self.assertEqual(RUNTIME._command(Path("/usr/bin/node"), "--version"), "v22.16.0")
        arguments, options = query.call_args
        self.assertEqual(arguments[0], ["/usr/bin/node", "--version"])
        self.assertEqual(options["cwd"], "/")
        self.assertEqual(options["timeout"], 10)
        self.assertNotIn("GH_TOKEN", options["env"])
        self.assertNotIn("shell", options)
        for failure in (subprocess.TimeoutExpired("private-command", 10),
                        subprocess.CalledProcessError(1, "private-command", stderr="private-output"), OSError("private-path")):
            with patch.object(RUNTIME.subprocess, "run", side_effect=failure), self.assertRaises(RUNTIME.RuntimeIdentityError) as raised:
                RUNTIME._command(Path("/usr/bin/node"), "--version")
            self.assertNotIn("private", str(raised.exception))

    def test_requirements_include_transitive_pins_and_reject_unsupported_syntax(self):
        with tempfile.TemporaryDirectory(prefix="overte-runtime-requirements-") as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            host = root / "tests/requirements-host.txt"
            host.write_text("-r requirements-repository.txt\nPillow==12.3.0\n", encoding="utf-8")
            (root / "tests/requirements-repository.txt").write_text("PyYAML==6.0.3\n", encoding="utf-8")
            self.assertEqual(RUNTIME._requirements(root), {"pillow": "12.3.0", "pyyaml": "6.0.3"})
            for source in ("Pillow>=12\n", "--index-url https://private.example\n", "-r /etc/passwd\n",
                           "Pillow==12.3.0\nPillow==12.4.0\n"):
                with self.subTest(source=source):
                    host.write_text(source, encoding="utf-8")
                    with self.assertRaises(RUNTIME.RuntimeIdentityError):
                        RUNTIME._requirements(root)

    def test_actual_controller_bytes_and_recursive_requirements_are_bound_without_global_registry_hash(self):
        with tempfile.TemporaryDirectory(prefix="overte-trusted-runtime-") as temporary:
            root = Path(temporary)
            for relative in RUNTIME._TRUSTED_EXECUTION_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# reviewed original controller\n", encoding="utf-8")
            (root / "tests/requirements-host.txt").write_text("-r requirements-repository.txt\nPillow==12.3.0\n", encoding="utf-8")
            (root / "tests/requirements-repository.txt").write_text("PyYAML==6.0.3\n", encoding="utf-8")
            (root / ".github").mkdir()
            registry = root / ".github/test-suites.json"
            registry.write_text('{"suites":{"unrelated":"original"}}\n', encoding="utf-8")
            required, manifests = RUNTIME._requirement_inventory(root)
            original = RUNTIME._trusted_execution(manifests, root)
            self.assertEqual(required, {"pillow": "12.3.0", "pyyaml": "6.0.3"})
            self.assertIn("tests/requirements-repository.txt", original)
            self.assertNotIn(".github/test-suites.json", original)
            # The candidate tree can remain unchanged while trusted main has a
            # new process controller; the actual runtime identity must differ.
            (root / "tools/test-evidence/execution.py").write_text("# reviewed corrected controller\n", encoding="utf-8")
            updated = RUNTIME._trusted_execution(manifests, root)
            self.assertNotEqual(original, updated)
            registry.write_text('{"suites":{"unrelated":"changed"}}\n', encoding="utf-8")
            self.assertEqual(updated, RUNTIME._trusted_execution(manifests, root))
            (root / "tests/requirements-repository.txt").write_text("PyYAML==6.0.4\n", encoding="utf-8")
            _, changed_manifests = RUNTIME._requirement_inventory(root)
            self.assertNotEqual(updated, RUNTIME._trusted_execution(changed_manifests, root))

    def test_python_distribution_inventory_requires_actual_trusted_pins(self):
        distribution = SimpleNamespace(metadata={"Name": "PyYAML"}, version="6.0.3")
        with patch.object(RUNTIME.sysconfig, "get_paths", return_value={"purelib": "/venv/site-packages", "platlib": "/venv/site-packages"}), \
                patch.object(RUNTIME.metadata, "distributions", return_value=[distribution]) as discover:
            self.assertEqual(RUNTIME._python_packages({"pyyaml": "6.0.3"}), {"pyyaml": "6.0.3"})
            self.assertEqual(discover.call_args.kwargs["path"], ["/venv/site-packages"])
            with self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._python_packages({"pyyaml": "6.0.4"})
        with patch.object(RUNTIME.metadata, "distributions", return_value=[distribution, distribution]), self.assertRaises(RUNTIME.RuntimeIdentityError):
            RUNTIME._python_packages({"pyyaml": "6.0.3"})

    def test_debian_inventory_records_actual_versions_and_requires_glm(self):
        with patch.object(RUNTIME, "_checked_executable", return_value=Path("/usr/bin/dpkg-query")), \
                patch.object(RUNTIME, "_command", return_value="libglm-dev\t1.0.1-1\tinstall ok installed\nlibqt6core6t64:amd64\t6.4.2\tinstall ok installed"):
            self.assertEqual(RUNTIME._debian_packages(), {"libglm-dev": "1.0.1-1", "libqt6core6t64:amd64": "6.4.2"})
        for source in ("libqt6core6t64:amd64\t6.4.2\tinstall ok installed", "malformed output"):
            with patch.object(RUNTIME, "_checked_executable", return_value=Path("/usr/bin/dpkg-query")), \
                    patch.object(RUNTIME, "_command", return_value=source), self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._debian_packages()

    def test_os_and_runner_identity_require_actual_supported_values(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(RUNTIME.platform, "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "24.04"}))
            stack.enter_context(patch.object(RUNTIME.platform, "system", return_value="Linux"))
            stack.enter_context(patch.object(RUNTIME.platform, "machine", return_value="x86_64"))
            stack.enter_context(patch.object(RUNTIME.platform, "release", return_value="6.11.0"))
            stack.enter_context(patch.object(RUNTIME.Path, "read_text", return_value="0\n"))
            stack.enter_context(patch.object(RUNTIME, "_file_digest", return_value="sha256:" + "a" * 64))
            stack.enter_context(patch.dict(RUNTIME.os.environ, _BASE_ENVIRONMENT, clear=True))
            identity = RUNTIME._os_identity()
            self.assertEqual(identity["architecture"], "x86_64")
            self.assertEqual(identity["runner"]["ImageVersion"], "20261001.1.0")
            with patch.dict(RUNTIME.os.environ, {"ImageVersion": ""}), self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._os_identity()
            with patch.object(RUNTIME.platform, "machine", return_value="unknown"), self.assertRaises(RUNTIME.RuntimeIdentityError):
                RUNTIME._os_identity()


if __name__ == "__main__":
    unittest.main()
