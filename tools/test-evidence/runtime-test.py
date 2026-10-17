#!/usr/bin/env python3
"""Offline runtime-identity tests; no host queries, installs or builds."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import venv

import inputs


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
            stack.enter_context(patch.object(RUNTIME, "_python_lookup_identity", return_value={
                "mode": "controller-virtualenv", "aliases": ["python", "python3"], "include_system_site_packages": False,
                "user_site_enabled": False}))
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

    def test_reviewed_composer_search_path_does_not_allow_neighboring_user_paths(self):
        composer = "/home/runner/.config/composer/vendor/bin"
        self.assertEqual(self.capture({"PATH": composer + ":/usr/bin:/bin"}), self.capture())
        for directory in (composer + "/child", composer + "-other", "/other/.config/composer/vendor/bin"):
            with self.subTest(directory=directory), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture({"PATH": directory + ":/usr/bin:/bin"})

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

    def test_actual_controller_venv_bin_is_supported_but_other_workspace_bins_are_not(self):
        actual_bin = Path(sys.executable).parent
        self.capture({"PATH": str(actual_bin) + ":/usr/bin:/bin"})
        with self.assertRaises(RUNTIME.RuntimeIdentityError):
            self.capture({"PATH": "/workspace/another-venv/bin:/usr/bin:/bin"})

    def test_python_aliases_bind_effective_venv_instead_of_only_the_shared_binary(self):
        with tempfile.TemporaryDirectory(prefix="overte-python-lookup-") as temporary:
            prefix = Path(temporary) / "host-env"
            venv.EnvBuilder(with_pip=False, symlinks=True).create(prefix)
            executable = prefix / "bin/python"
            with patch.object(RUNTIME.sys, "executable", str(executable)), \
                    patch.object(RUNTIME.sys, "prefix", str(prefix)), \
                    patch.object(RUNTIME.site, "ENABLE_USER_SITE", False), \
                    patch.dict(RUNTIME.os.environ, {"PATH": str(prefix / "bin") + ":/usr/bin:/bin", "VIRTUAL_ENV": str(prefix)}):
                identity = RUNTIME._python_lookup_identity()
                self.assertEqual(identity, {"mode": "controller-virtualenv", "aliases": ["python", "python3"],
                                            "include_system_site_packages": False, "user_site_enabled": False})
                self.assertNotIn(str(prefix), json.dumps(identity))
                with patch.object(RUNTIME.site, "ENABLE_USER_SITE", True), \
                        self.assertRaises(RUNTIME.RuntimeIdentityError):
                    RUNTIME._python_lookup_identity()
                for observed in ({"prefix": sys.base_prefix, "base_prefix": sys.base_prefix, "user_site": False},
                                 {"prefix": str(prefix), "base_prefix": sys.base_prefix, "user_site": True}):
                    with self.subTest(observed=observed), patch.object(RUNTIME, "_command", return_value=json.dumps(observed)), \
                            self.assertRaises(RUNTIME.RuntimeIdentityError):
                        RUNTIME._python_lookup_identity()
                with patch.dict(RUNTIME.os.environ, {"PATH": "/usr/bin:/bin:" + str(prefix / "bin")}), \
                        self.assertRaises(RUNTIME.RuntimeIdentityError):
                    RUNTIME._python_lookup_identity()
                with patch.dict(RUNTIME.os.environ, {"VIRTUAL_ENV": "/unrelated/prefix"}), \
                        self.assertRaises(RUNTIME.RuntimeIdentityError):
                    RUNTIME._python_lookup_identity()
                config = prefix / "pyvenv.cfg"
                config.write_text(config.read_text().replace("include-system-site-packages = false", "include-system-site-packages = true"))
                with self.assertRaises(RUNTIME.RuntimeIdentityError):
                    RUNTIME._python_lookup_identity()

    def test_only_exact_fixed_git_capture_overrides_are_supported(self):
        identity = self.capture(dict(RUNTIME._FIXED_GIT_OVERRIDES))
        self.assertEqual(identity["flags"]["git_process_overrides"], "maintenance-disabled")
        for overrides in ({"GIT_CONFIG_COUNT": "2"}, dict(RUNTIME._FIXED_GIT_OVERRIDES) | {"GIT_CONFIG_VALUE_0": "true"},
                          dict(RUNTIME._FIXED_GIT_OVERRIDES) | {"GIT_CONFIG_KEY_9": "other"}):
            with self.subTest(overrides=overrides), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture(overrides)

    def test_shared_immutable_git_exception_is_exact_and_distinct(self):
        values = dict(RUNTIME._FIXED_GIT_OVERRIDES) | {"GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_2": "safe.directory",
                                                    "GIT_CONFIG_VALUE_2": "/work"}
        identity = self.capture(values)
        self.assertEqual(identity["flags"]["git_process_overrides"], "maintenance-disabled-safe-work")
        for key, value in (("GIT_CONFIG_VALUE_2", "*"), ("GIT_CONFIG_VALUE_2", "/work/elsewhere"),
                           ("GIT_CONFIG_KEY_2", "include.path"), ("GIT_CONFIG_COUNT", "2")):
            with self.subTest(key=key, value=value), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture(values | {key: value})

    def test_standard_hosted_path_allows_only_the_identified_system_jdk_directory(self):
        java_home = Path("/usr/lib/jvm/temurin-17-jdk-amd64")
        standard_path = ":".join((
            "/opt/hostedtoolcache/Python/3.12.12/x64/bin", "/opt/hostedtoolcache/node/22/x64/bin",
            str(java_home / "bin"), "/home/runner/.cargo/bin", "/home/linuxbrew/.linuxbrew/bin",
            "/home/linuxbrew/.linuxbrew/sbin", "/home/runner/.ghcup/bin", "/usr/local/.ghcup/bin",
            "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin",
            "/usr/local/games", "/usr/games", "/home/runner/.dotnet/tools",
            "/home/runner/.local/share/powershell", "/home/runner/.local/bin", "/opt/pipx_bin", "/snap/bin",
            "/home/runner/.config/composer/vendor/bin",
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
            (root / ".github").mkdir(exist_ok=True)
            registry = root / ".github/test-suites.json"
            registry.write_text('{"suites":{"unrelated":"original"}}\n', encoding="utf-8")
            required, manifests = RUNTIME._requirement_inventory(root)
            original = RUNTIME._controller_file_hashes(manifests, root)
            self.assertEqual(required, {"pillow": "12.3.0", "pyyaml": "6.0.3"})
            self.assertIn("tests/requirements-repository.txt", original)
            self.assertNotIn(".github/test-suites.json", original)
            # The candidate tree can remain unchanged while trusted main has a
            # new process controller; the actual runtime identity must differ.
            (root / "tools/test-evidence/execution.py").write_text("# reviewed corrected controller\n", encoding="utf-8")
            updated = RUNTIME._controller_file_hashes(manifests, root)
            self.assertNotEqual(original, updated)
            registry.write_text('{"suites":{"unrelated":"changed"}}\n', encoding="utf-8")
            self.assertEqual(updated, RUNTIME._controller_file_hashes(manifests, root))
            (root / "tests/requirements-repository.txt").write_text("PyYAML==6.0.4\n", encoding="utf-8")
            _, changed_manifests = RUNTIME._requirement_inventory(root)
            self.assertNotEqual(updated, RUNTIME._controller_file_hashes(changed_manifests, root))

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


class IsolatedPreparedIdentityTests(unittest.TestCase):
    def setUp(self):
        self.base = RuntimeIdentityTests().capture()
        self.python = Path('/opt/hostedtoolcache/Python') / self.base['python']['version'] / 'x64'
        self.node = Path('/opt/hostedtoolcache/node') / self.base['tools']['node']['version'][1:] / 'x64'
        self.java = Path(inputs.ISOLATED_JDK)
        self.roots = dict.fromkeys((inputs.ISOLATED_VENV, str(self.python), str(self.node), str(self.java)),
                                   'sha256:' + 'a' * 64)

    def capture(self, roots=None, *, certificate=False, python=None, node=None, java=None):
        with (patch.object(RUNTIME, 'capture_host_environment', return_value=deepcopy(self.base)),
              patch.object(RUNTIME.sys, 'prefix', inputs.ISOLATED_VENV),
              patch.object(RUNTIME.sys, 'base_prefix', str(self.python if python is None else python)),
              patch.object(RUNTIME.Path, 'resolve', lambda path, **_kwargs: Path(inputs.ISOLATED_CACERTS)
                           if certificate and path == self.java / 'lib/security/cacerts' else path),
              patch.object(RUNTIME.Path, 'is_symlink', return_value=certificate),
              patch.object(RUNTIME.os, 'readlink', return_value=inputs.ISOLATED_CACERTS),
              patch.object(RUNTIME, '_checked_executable', return_value=(self.node if node is None else node) / 'bin/node'),
              patch.object(RUNTIME, '_identified_java_home', return_value=self.java if java is None else java)):
            return RUNTIME.capture_isolated_host_environment(self.roots if roots is None else roots)

    def test_actual_prepared_identity_is_mandatory_versioned_and_copied_inside_capture(self):
        original = deepcopy(self.base)
        value = self.capture()
        self.assertEqual(value['schema'], 3)
        self.assertEqual(value['profile'], inputs.ISOLATED_FULL_PROFILE)
        self.assertEqual(value['prepared'], {'schema': 1, 'roots': self.roots, 'external_inputs': []})
        self.assertEqual(self.base, original, 'legacy capture shape is unchanged')
        self.roots[inputs.ISOLATED_VENV] = 'sha256:' + 'b' * 64
        self.assertNotEqual(value['prepared']['roots'], self.roots, 'E cannot alias its mutable binding')
        self.assertNotEqual(value, self.capture(), 'same versions with different prepared bytes must differ in E')

    def test_actual_tool_roots_cannot_be_replaced_by_supplied_digest_paths(self):
        for override in ({'python': Path('/other/python')}, {'node': Path('/usr')}, {'java': Path('/usr/lib/jvm/other')}):
            with self.subTest(override=override), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture(**override)
        for roots in ({}, {**self.roots, '/unknown': 'sha256:' + 'a' * 64},
                      {**self.roots, inputs.ISOLATED_VENV: 'unknown'}):
            with self.subTest(roots=roots), self.assertRaises(RUNTIME.RuntimeIdentityError):self.capture(roots)

    def test_actual_fixed_certificate_selection_cannot_be_omitted_or_invented(self):
        roots = {**self.roots, inputs.ISOLATED_CACERTS: 'sha256:' + 'c' * 64}
        value = self.capture(roots, certificate=True)
        self.assertEqual(value['prepared']['external_inputs'], [inputs.ISOLATED_CACERTS])
        for selected, supplied in ((True, self.roots), (False, roots)):
            with self.subTest(selected=selected), self.assertRaises(RUNTIME.RuntimeIdentityError):
                self.capture(supplied, certificate=selected)

    def test_fresh_tiny_boundary_projection_imports_without_repository_inputs(self):
        with tempfile.TemporaryDirectory(prefix='overte-boundary-import-') as temporary:
            destination = Path(temporary)
            scripts = destination / 'tools/test-evidence'
            scripts.mkdir(parents=True)
            for name in ('runtime.py', 'sandbox_probe.py'):
                (scripts / name).write_bytes(Path(__file__).with_name(name).read_bytes())
            (destination / 'readonly-canary').write_text('fixed-boundary-fixture')
            code = ('import importlib.util,sys;'
                'assert importlib.util.find_spec("inputs") is None;'
                's=importlib.util.spec_from_file_location("tiny_probe",sys.argv[1]);'
                'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
                'assert "inputs" not in sys.modules;'
                'assert callable(m.runtime.capture_host_environment)')
            result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(scripts/'sandbox_probe.py')],
                cwd=destination, env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(Path(__file__).parent)},
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)



class ProtectedPairControllerIdentityTests(unittest.TestCase):
    def test_pair_controller_bytes_are_actual_E_inputs_and_old_serial_identity_differs(self):
        files=('tools/test-evidence/sandbox_host.py','tools/test-evidence/sandbox_shared.py',
               'tools/test-evidence/producer_workflow.py')
        self.assertTrue(set(files)<=set(RUNTIME._TRUSTED_EXECUTION_FILES))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in RUNTIME._TRUSTED_EXECUTION_FILES:
                leaf=root/name;leaf.parent.mkdir(parents=True,exist_ok=True);leaf.write_text('version unchanged; serial')
            current=RUNTIME._controller_file_hashes({},root)
            old_serial={name:value for name,value in current.items() if name not in files}
            self.assertNotEqual(old_serial,current)
            for name in files:
                with self.subTest(name=name):
                    leaf=root/name;before=leaf.read_bytes();leaf.write_text('version unchanged; two separate scopes')
                    changed=RUNTIME._controller_file_hashes({},root)
                    self.assertNotEqual(current[name],changed[name])
                    self.assertEqual({k:v for k,v in current.items() if k!=name},
                                     {k:v for k,v in changed.items() if k!=name})
                    leaf.write_bytes(before)


if __name__ == "__main__":
    unittest.main()
