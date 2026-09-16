#!/usr/bin/env python3
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class DomainDiagnostics(unittest.TestCase):
    def test_original_payloads_settings_and_redirect(self):
        source = (ROOT / "libraries/networking/src/DomainHandler.cpp").read_text()
        calls = re.findall(r"\bq(?:CDebug|CWarning|Debug|Warning)\([^;]+;", source)
        self.assertEqual(len(calls), 30)
        for call in calls:
            self.assertRegex(call, r"^q(?:CDebug|CWarning)\(networking(?:_ice)?\) << "
                             r"overte::security::diagnosticEvent\(overte::security::DiagnosticEvent::Redacted\);$")
        self.assertNotRegex(source, r"\b(?:printf|fprintf|qCritical|qInfo|qFatal|HIFI_FCDEBUG)\s*\(|std::(?:cout|cerr)")
        methods = []
        for name in ("processSettingsPacketList", "setRedirectErrorState"):
            methods.append("void DomainHandler::" + name + "(" + source.split(
                "void DomainHandler::" + name + "(", 1)[1].split("\n}", 1)[0] + "\n}\n")
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="px16-domain-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "domain-payloads.inc").write_text("\n".join(calls))
            (temporary / "domain-methods.inc").write_text("\n".join(methods))
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-I", str(ROOT), "-I", str(temporary),
                            str(pathlib.Path(__file__).with_name("domain-diagnostics-test.cpp")), "-o", str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
