#!/usr/bin/env python3
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class ScopedHostname(unittest.TestCase):
    def test_original_lookup_and_real_qt_resolver(self):
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Network"], text=True))
        driver = pathlib.Path(__file__).with_name("scoped-hostname-test.cpp")
        domain = (ROOT / "libraries/networking/src/DomainHandler.cpp").read_text()
        binding = "_hostnameLookup.start(" + domain.split("_hostnameLookup.start(", 1)[1].split("});", 1)[0] + "});"
        with tempfile.TemporaryDirectory(prefix="sh005-dns-") as temporary:
            (pathlib.Path(temporary) / "domain-lookup-binding.inc").write_text(binding)
            for boundary in (True, False):
                with self.subTest(resolver_boundary=boundary):
                    binary = pathlib.Path(temporary) / ("boundary" if boundary else "qt")
                    subprocess.run(["c++", "-std=c++17", "-fPIC", "-I", str(ROOT), "-I", temporary,
                                    *(["-DTEST_RESOLVER_BOUNDARY"] if boundary else []),
                                    str(driver), "-o", str(binary), *flags], check=True, timeout=30)
                    subprocess.run(["unshare", "--user", "--map-root-user", "--net",
                                    str(binary)], check=True, timeout=5)

    def test_actual_domain_production_binding(self):
        source = (ROOT / "libraries/networking/src/DomainHandler.cpp").read_text()
        header = (ROOT / "libraries/networking/src/DomainHandler.h").read_text()
        reset = source.split("void DomainHandler::hardReset(QString reason) {", 1)[1].split("\n}", 1)[0]
        self.assertTrue(reset.lstrip().startswith("_hostnameLookup.cancel();"))
        self.assertIn("overte::network::ScopedHostnameLookup _hostnameLookup;", header)
        binding = source.split("_hostnameLookup.start(", 1)[1].split("});", 1)[0]
        self.assertEqual(binding.strip(), "domainURL.host(), this, [this](const QHostInfo& info) {\n                        completedHostnameLookup(info);")
        self.assertNotIn("QHostInfo::lookupHost(", source)
        # Real callback remains the only socket setter; generation guard runs
        # before entering it. No domain URL comparison is used as a ticket.
        callback = source.split("void DomainHandler::completedHostnameLookup(", 1)[1].split("\n}", 1)[0]
        self.assertIn("_sockAddr.setAddress(hostInfo.addresses()[i]);", callback)


if __name__ == "__main__":
    unittest.main()
