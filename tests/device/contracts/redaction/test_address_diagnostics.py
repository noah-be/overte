#!/usr/bin/env python3
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class AddressDiagnostics(unittest.TestCase):
    def test_original_payloads_and_error_behavior(self):
        source = (ROOT / "libraries/networking/src/AddressManager.cpp").read_text()
        calls = re.findall(r"qC(?:Debug|Warning)\([^;]+;", source)
        self.assertEqual(len(calls), 19)
        for call in calls:
            self.assertRegex(call, r"^qC(?:Debug|Warning)\(networking(?:_ice)?\) << "
                             r"overte::security::diagnosticEvent\(overte::security::DiagnosticEvent::"
                             r"(?:ConnectionFailed|UrlRejected|Redacted)\);$")
        # Any new direct printf/raw Qt/frequency sink needs an explicit review.
        self.assertNotRegex(source, r"\b(?:printf|fprintf|qDebug|qWarning|qCritical|HIFI_FCDEBUG)\s*\(")
        method = "void AddressManager::handleAPIError(" + source.split(
            "void AddressManager::handleAPIError(", 1)[1].split("\n}", 1)[0] + "\n}\n"
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Network"], text=True))
        driver = pathlib.Path(__file__).with_name("address-diagnostics-test.cpp")
        with tempfile.TemporaryDirectory(prefix="px16-address-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "address-api-error.inc").write_text(method)
            (temporary / "address-diagnostic-expressions.inc").write_text("\n".join(calls))
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-I", str(ROOT), "-I", str(temporary),
                            str(driver), "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_activity_destination_is_closed_at_all_four_callers(self):
        source = (ROOT / "libraries/networking/src/AddressManager.cpp").read_text()
        calls = re.findall(r"UserActivityLogger::getInstance\(\)\.wentTo\([^;]+;", source)
        self.assertEqual(len(calls), 4)
        for call in calls:
            self.assertRegex(call, r'^UserActivityLogger::getInstance\(\)\.wentTo\(trigger, '
                             r'URL_TYPE_(?:USER|NETWORK_ADDRESS|DOMAIN_ID|PLACE), QStringLiteral\("OVT_REDACTED"\)\);$')


if __name__ == "__main__":
    unittest.main()
