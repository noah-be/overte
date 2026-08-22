#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sanitizer", ROOT / "ios/tools/sanitize-ci-log.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
raw = b"build started\nTOKEN=abc123\nhttps://user:pass@example.test/x\npassword: hunter2\nbuild failed\n"
clean = module.sanitize(raw)
assert "abc123" not in clean and "hunter2" not in clean and "user:pass" not in clean
assert clean.startswith("build started") and clean.endswith("build failed\n")
assert "private-prefix" not in module.sanitize(b"private-prefix\n" + b"x" * (module.MAX_BYTES + 1))
print("PASS integrated CI log sanitizer tests")
