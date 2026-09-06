import re
import ast
import os
import shlex
from types import SimpleNamespace
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CMakeSourceOnlyContractTest(unittest.TestCase):
    def test_only_source_archives_are_bound(self):
        data = (ROOT / "conandata.yml").read_text(encoding="utf-8")
        self.assertIn("cmake-3.31.12.tar.gz", data)
        self.assertIn("cmake-4.4.0.tar.gz", data)
        self.assertNotRegex(data, re.compile(r"linux-(?:x86_64|aarch64)\.tar"))

    def test_recipe_bootstraps_without_package_manager_or_binary_download(self):
        recipe = (ROOT / "conanfile.py").read_text(encoding="utf-8")
        self.assertIn("bootstrap", recipe)
        self.assertIn("--no-system-libs", recipe)
        self.assertNotRegex(
            recipe,
            re.compile(r"(?i)(sudo|apt(?:-get)?|dnf|yum|pacman|wget|curl)"),
        )

    def test_actual_build_disables_only_host_tls_and_package_keeps_license(self):
        tree = ast.parse((ROOT / "conanfile.py").read_text(encoding="utf-8"))
        recipe = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        methods = [node for node in recipe.body if isinstance(node, ast.FunctionDef) and node.name in ("build", "package")]
        module = ast.Module(body=methods, type_ignores=[])
        calls, copies = [], []
        scope = {"os": os, "shlex": shlex, "build_jobs": lambda _: 6,
                 "copy": lambda *args, **kwargs: copies.append((args, kwargs))}
        exec(compile(module, "actual-cmake-recipe-methods", "exec"), scope)
        instance = SimpleNamespace(source_folder="/source tree", package_folder="/package tree", run=calls.append)
        scope["build"](instance)
        self.assertEqual(shlex.split(calls[0]), ["/source tree/bootstrap", "--prefix=/package tree", "--parallel=6",
                                               "--no-qt-gui", "--no-system-libs", "--", "-DCMAKE_USE_OPENSSL=OFF"])
        self.assertEqual(calls[1], "make -j6")
        scope["package"](instance)
        self.assertEqual(copies[0][1]["src"], "/source tree")
        self.assertEqual(copies[0][0][1], "Copyright.txt")


if __name__ == "__main__":
    unittest.main()
