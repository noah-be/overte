"""Bind shader generators to completed source-built Linux packages, offline."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct


TOOLS = {
    "scribe": ("SCRIBE_DIR", "tools/scribe"),
    "glslang": ("GLSLANG_DIR", "bin/glslangValidator"),
    "spirv-cross": ("SPIRV_CROSS_DIR", "bin/spirv-cross"),
    "spirv-tools": ("SPIRV_TOOLS_DIR", "bin/spirv-opt"),
}


def stage(attempt, source_commit):
    attempt = Path(attempt).resolve(strict=True)
    graph_path = attempt / "host-tools-result.json"
    graph_bytes = graph_path.read_bytes()
    digest = hashlib.sha256(graph_bytes).hexdigest()
    checkpoint = (attempt / "checkpoints/host-tools.COMPLETE").read_text().splitlines()
    for field in ("name=host-tools", f"source_commit={source_commit}",
                  f"result_sha256={digest}", f"attempt_root={attempt}"):
        if checkpoint.count(field) != 1:
            raise ValueError("completed host-tools checkpoint binding mismatch")
    nodes = json.loads(graph_bytes)["graph"]["nodes"].values()
    selected = {}
    for node in nodes:
        name = (node.get("ref") or "").split("/", 1)[0]
        if name not in TOOLS:
            continue
        settings = node.get("settings", {})
        if (name in selected or node.get("context") != "host"
                or settings.get("os") != "Linux" or settings.get("arch") != "x86_64"
                or node.get("binary") != "Build" or node.get("remote") is not None
                or node.get("binary_remote") is not None):
            raise ValueError("host tool must have one source-built Linux package")
        variable, relative = TOOLS[name]
        package = Path(node["package_folder"]).resolve(strict=True)
        package.relative_to((attempt / "conan/p").resolve(strict=True))
        executable = (package / relative).resolve(strict=True)
        executable.relative_to(package)
        with executable.open("rb") as stream:
            header = stream.read(20)
        if (header[:6] != b"\x7fELF\x02\x01" or len(header) < 20
                or struct.unpack_from("<H", header, 18)[0] != 62
                or not os.access(executable, os.X_OK)):
            raise ValueError("host tool is not an executable x86_64 ELF")
        # CMake quoted arguments must not interpret a path as source code.
        if any(char in str(executable.parent) for char in ('"', '$', ';', '\\', '\n', '\r')):
            raise ValueError("host tool path cannot be represented safely in CMake")
        selected[name] = {
            "variable": variable, "executable": str(executable),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "ref": node["ref"], "package_id": node["package_id"], "prev": node["prev"],
        }
    if set(selected) != set(TOOLS):
        raise ValueError("required source-built host tool is absent")
    output = attempt / "target/fdroid-host-tools.cmake"
    text = "# Generated from the completed Linux source-build checkpoint.\n"
    for tool in selected.values():
        text += f'set(ENV{{{tool["variable"]}}} "{Path(tool["executable"]).parent}")\n'
    temporary = output.with_suffix(".cmake.new")
    temporary.write_text(text)
    temporary.replace(output)
    output.with_suffix(".json").write_text(json.dumps({
        "source_commit": source_commit, "host_graph_sha256": digest, "tools": selected,
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    stage(args.attempt_root, args.source_commit)
