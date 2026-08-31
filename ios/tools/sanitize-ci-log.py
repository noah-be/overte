#!/usr/bin/env python3
"""Create a size-bounded, secret-redacted CI diagnostic log."""
import re, sys
from pathlib import Path
MAX_BYTES = 2 * 1024 * 1024
PATTERNS = (
    re.compile(r"(?i)(password|passwd|token|secret|authorization|keychain_password|apple_id)(\s*[:=]\s*)([^\s]+)"),
    re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)
def sanitize(payload: bytes) -> str:
    text = payload[-MAX_BYTES:].decode("utf-8", errors="replace")
    text = PATTERNS[0].sub(r"\1\2[REDACTED]", text)
    text = PATTERNS[1].sub(r"\1[REDACTED]@", text)
    return PATTERNS[2].sub("[REDACTED PRIVATE KEY]", text)
def main() -> int:
    if len(sys.argv) != 3: return 2
    source, output = map(Path, sys.argv[1:])
    if not source.is_file() or source.resolve() == output.resolve(): return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sanitize(source.read_bytes()), encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
