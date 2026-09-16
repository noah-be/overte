#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


helper = Path(__file__).resolve().parents[1] / "ci/client-compiler-cache-key.py"
spec = importlib.util.spec_from_file_location("client_cache_key", helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    compiler = root / "clang"
    compiler.write_bytes(b"test compiler identity")
    args = [str(compiler), "ARM64", "17F113", "23F70", "26.5"]
    original = module.identity(*args)
    baseline = module.outputs(original, "100", "1")
    # Immutable snapshot run IDs vary, but the compiler lookup buster must not.
    rerun = module.outputs(module.identity(*args), "101", "2")
    assert baseline["namespace"] == rerun["namespace"]
    assert baseline["key"] != rerun["key"]
    # Cache identity is content-based, independent of checkout/runner path.
    relocated = root / "other-clang"
    relocated.write_bytes(compiler.read_bytes())
    assert module.identity(str(relocated), *args[1:]) == original
    # Native compiler / SDK / architecture changes must never share this buster.
    for index, changed in ((1, "X64"), (2, "17F114"), (3, "23F71"), (4, "26.6")):
        variant = args.copy()
        variant[index] = changed
        assert module.outputs(module.identity(*variant), "100", "1")["namespace"] != baseline["namespace"]
    compiler.write_bytes(b"different compiler")
    assert module.outputs(module.identity(*args), "100", "1")["namespace"] != baseline["namespace"]
    compiler.write_bytes(b"test compiler identity")
    for bad in ("", "26.5\nnamespace=forged", "../sdk"):
        try:
            module.identity(*args[:4], bad)
            raise AssertionError("malformed toolchain identity accepted")
        except ValueError:
            pass
    output = root / "github-output"
    environment = root / "github-env"
    environment.write_text("EXISTING_SETTING=retained\n")
    command = [sys.executable, str(helper), "--compiler", str(compiler), "--arch", "ARM64",
               "--xcode-build", "17F113", "--sdk-build", "23F70", "--sdk-version", "26.5",
               "--run-id", "100", "--run-attempt", "1", "--github-output", str(output),
               "--github-env", str(environment)]
    receipt = json.loads(subprocess.check_output(command, text=True))
    assert receipt["outputs"] == baseline
    assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == baseline
    assert environment.read_text() == f"EXISTING_SETTING=retained\nSCCACHE_C_CUSTOM_CACHE_BUSTER={baseline['namespace']}\n"
    compiler.write_bytes(b"")
    failed = subprocess.run(command, capture_output=True, text=True)
    assert failed.returncode != 0 and "nonempty" in failed.stderr
    assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == baseline
    assert environment.read_text() == f"EXISTING_SETTING=retained\nSCCACHE_C_CUSTOM_CACHE_BUSTER={baseline['namespace']}\n"

print("PASS compiler compatibility identity: stable runs/paths, native input invalidation, safe CLI outputs")
