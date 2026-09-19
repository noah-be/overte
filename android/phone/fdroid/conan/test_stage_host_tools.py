import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from stage_host_tools import TOOLS, stage


class HostToolsStageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "target").mkdir()
        (self.root / "checkpoints").mkdir()
        self.source = "a" * 40
        self.nodes = {}
        for number, (name, (_, relative)) in enumerate(TOOLS.items()):
            package = self.root / "conan/p" / name / "p"
            executable = package / relative
            executable.parent.mkdir(parents=True)
            header = bytearray(64)
            header[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<H", header, 18, 62)
            executable.write_bytes(header)
            executable.chmod(0o755)
            self.nodes[str(number)] = {
                "ref": name + "/1#" + "b" * 32, "package_id": "c" * 40,
                "prev": "d" * 32, "context": "host", "binary": "Build",
                "settings": {"os": "Linux", "arch": "x86_64"},
                "package_folder": str(package),
            }

    def write_inputs(self):
        data = json.dumps({"graph": {"nodes": self.nodes}}).encode()
        (self.root / "host-tools-result.json").write_bytes(data)
        (self.root / "checkpoints/host-tools.COMPLETE").write_text(
            f"name=host-tools\nsource_commit={self.source}\n"
            f"attempt_root={self.root}\nresult_sha256={hashlib.sha256(data).hexdigest()}\n")

    def test_completed_linux_tools_are_bound(self):
        self.write_inputs()
        stage(self.root, self.source)
        report = json.loads((self.root / "target/fdroid-host-tools.json").read_text())
        self.assertEqual(set(report["tools"]), set(TOOLS))
        for tool in report["tools"].values():
            self.assertEqual(tool["sha256"], hashlib.sha256(Path(tool["executable"]).read_bytes()).hexdigest())

    def test_rejects_wrong_architecture_cache_and_remote(self):
        for field, value in (("settings", {"os": "Android", "arch": "armv8"}),
                             ("binary", "Cache"), ("remote", "foreign")):
            with self.subTest(field=field):
                original = self.nodes["0"].copy()
                self.nodes["0"][field] = value
                self.write_inputs()
                with self.assertRaises(ValueError):
                    stage(self.root, self.source)
                self.nodes["0"] = original

    def test_rejects_android_elf_even_with_linux_metadata(self):
        executable = Path(self.nodes["0"]["package_folder"]) / "tools/scribe"
        header = bytearray(executable.read_bytes())
        struct.pack_into("<H", header, 18, 183)
        executable.write_bytes(header)
        self.write_inputs()
        with self.assertRaises(ValueError):
            stage(self.root, self.source)

    def test_rejects_missing_or_duplicate_tool(self):
        node = self.nodes.pop("0")
        self.write_inputs()
        with self.assertRaises(ValueError):
            stage(self.root, self.source)
        self.nodes["0"] = node
        self.nodes["duplicate"] = node.copy()
        self.write_inputs()
        with self.assertRaises(ValueError):
            stage(self.root, self.source)

    def test_rejects_changed_graph_or_source(self):
        self.write_inputs()
        with self.assertRaises(ValueError):
            stage(self.root, "e" * 40)
        with (self.root / "host-tools-result.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaises(ValueError):
            stage(self.root, self.source)

    def test_rejects_executable_symlink_escape(self):
        executable = Path(self.nodes["0"]["package_folder"]) / "tools/scribe"
        outside = self.root / "outside"
        executable.rename(outside)
        executable.symlink_to(outside)
        self.write_inputs()
        with self.assertRaises(ValueError):
            stage(self.root, self.source)


if __name__ == "__main__":
    unittest.main()
