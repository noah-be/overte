#!/usr/bin/env python3
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class NodeListDiagnostics(unittest.TestCase):
    def test_original_qt_payloads_and_username_reply(self):
        source = (ROOT / "libraries/networking/src/NodeList.cpp").read_text()
        calls = re.findall(r"\bq(?:CDebug|CWarning|Debug|Warning)\([^;]+;",source)
        self.assertEqual(len(calls),52)
        for call in calls:
            self.assertRegex(call,r"^q(?:CDebug|CWarning|Debug|Warning)\((?:networking(?:_ice)?)?\) << "
                             r"overte::security::diagnosticEvent\(overte::security::DiagnosticEvent::Redacted\);$")
        method = "void NodeList::processUsernameFromIDReply(" + source.split(
            "void NodeList::processUsernameFromIDReply(",1)[1].split("\n}",1)[0] + "\n}\n"
        flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","Qt6Core"],text=True))
        with tempfile.TemporaryDirectory(prefix="px16-nodelist-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "nodelist-diagnostic-expressions.inc").write_text("\n".join(calls))
            (temporary / "nodelist-user-reply.inc").write_text(method)
            binary = temporary / "test"
            subprocess.run(["c++","-std=c++17","-fPIC","-I",str(ROOT),"-I",str(temporary),
                            str(pathlib.Path(__file__).with_name("nodelist-diagnostics-test.cpp")),
                            "-o",str(binary),*flags],check=True,timeout=30)
            subprocess.run([str(binary)],check=True,timeout=5)

    def test_frequency_payload_is_closed_and_no_other_raw_sink(self):
        source = (ROOT / "libraries/networking/src/NodeList.cpp").read_text()
        frequency = re.findall(r"HIFI_FCDEBUG\([^;]+;",source)
        self.assertEqual(frequency,["HIFI_FCDEBUG(networking_ice(), DISABLED_CHECKIN_DEBUG);"])
        self.assertIn("static const QString DISABLED_CHECKIN_DEBUG{ QString::fromLatin1("
                      "overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted)) };",source)
        self.assertNotRegex(source,r"\b(?:printf|fprintf|qCritical|qInfo|qFatal)\s*\(|std::(?:cout|cerr)")


if __name__ == "__main__":
    unittest.main()
