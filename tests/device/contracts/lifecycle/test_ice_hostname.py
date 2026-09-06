#!/usr/bin/env python3
"""Complete production ICE setter/completion with original generation resolver."""
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class IceHostname(unittest.TestCase):
    def test_original_ice_setter_and_reset_fence(self):
        source = (ROOT / "libraries/networking/src/DomainHandler.cpp").read_text()
        setter = "void DomainHandler::setIceServerHostnameAndID(" + source.split(
            "void DomainHandler::setIceServerHostnameAndID(", 1)[1].split("void DomainHandler::activateICELocalSocket()", 1)[0]
        completion = "void DomainHandler::completedIceServerHostnameLookup()" + source.split(
            "void DomainHandler::completedIceServerHostnameLookup()", 1)[1].split("void DomainHandler::setIsConnected(", 1)[0]
        reset = source.split("void DomainHandler::hardReset(QString reason) {", 1)[1].split("emit resetting();", 1)[0]
        self.assertIn("_discoveryScope.next();", reset)
        self.assertIn("_iceHostnameLookup.cancel();", reset)
        self.assertNotIn("~SockAddr", setter)
        self.assertNotIn("&SockAddr::lookupCompleted", setter)
        header = (ROOT / "libraries/networking/src/DomainHandler.h").read_text()
        self.assertIn("overte::network::ScopedHostnameLookup _iceHostnameLookup;", header)
        lifecycle = "void DomainHandler::setClientDiscoveryVisibility(" + source.split(
            "void DomainHandler::setClientDiscoveryVisibility(", 1)[1].split("void DomainHandler::hardReset(", 1)[0]
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Network"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-ice-dns-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "ice-original.inc").write_text(lifecycle + setter + completion)
            (temporary / "ice-reset.inc").write_text(reset)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-I", str(ROOT), "-I", str(temporary),
                            str(pathlib.Path(__file__).with_name("ice-hostname-test.cpp")), "-o", str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
