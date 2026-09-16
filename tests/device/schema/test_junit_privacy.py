# SPDX-License-Identifier: Apache-2.0
"""Exercise the real JUnit producer, without any device commands."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('shared_device_runner', ROOT / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class JunitPrivacyTests(unittest.TestCase):
    def test_all_statuses_drop_raw_text_without_hiding_failures(self):
        secret = 'CANARY_SECRET_4451 token=a&b <private>target</private>'
        results = [dict(id='module-' + status, status=status, returncode=secret,
                        durationSeconds=0.5, output=secret)
                   for status in ('passed', 'failed', 'error', 'skipped')]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'junit.xml'
            runner.write_junit(results, path, 'smoke')
            raw = path.read_text()
            self.assertNotIn('CANARY', raw)
            self.assertNotIn('private', raw)
            root = ET.fromstring(raw)
            self.assertEqual(root.attrib['tests'], '4')
            for name in ('failures', 'errors', 'skipped'):
                self.assertEqual(root.attrib[name], '1')
            self.assertEqual(len(root.findall('./testcase/failure')), 1)
            self.assertEqual(len(root.findall('./testcase/error')), 1)
            self.assertEqual(len(root.findall('./testcase/skipped')), 1)
            for node in root.findall('./testcase/system-out'):
                self.assertEqual(node.text, 'OVT_REDACTED')
            self.assertEqual(root.find('./testcase/failure').attrib['message'], 'OVT_TEST_FAILED')
            self.assertEqual(root.find('./testcase/error').attrib['message'], 'OVT_TEST_INFRASTRUCTURE_ERROR')


if __name__ == '__main__':
    unittest.main()
