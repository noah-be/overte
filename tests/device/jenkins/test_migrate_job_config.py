#!/usr/bin/env python3
"""Device-free safety checks for Jenkins job migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "migrate_job_config", HERE / "migrate_job_config.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class JobMigrationTest(unittest.TestCase):
    def test_preserves_job_governance_and_replaces_only_pipeline_definition(self):
        with tempfile.TemporaryDirectory(prefix="overte-job-migration-") as name:
            root = Path(name)
            repository = root / "repo"
            repository.mkdir()
            (repository / ".git").mkdir()
            source = root / "source.xml"
            source.write_text(
                "<flow-definition><description>kept</description><properties>"
                "<example>kept</example></properties><definition class='old'>"
                "<script>legacy inline pipeline</script></definition><disabled>true</disabled>"
                "</flow-definition>", encoding="utf-8")
            destination = root / "destination.xml"
            MODULE.migrate(source, destination, str(repository), "test/e2e")
            value = ET.parse(destination).getroot()
            self.assertEqual("kept", value.findtext("description"))
            self.assertEqual("kept", value.findtext("properties/example"))
            self.assertEqual("true", value.findtext("disabled"))
            self.assertEqual(MODULE.SCRIPT_PATH, value.findtext("definition/scriptPath"))
            self.assertEqual("*/test/e2e", value.findtext(
                "definition/scm/branches/hudson.plugins.git.BranchSpec/name"))
            self.assertNotIn("legacy inline pipeline", destination.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
