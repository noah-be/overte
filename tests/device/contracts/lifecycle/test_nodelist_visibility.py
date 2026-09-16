#!/usr/bin/env python3
"""Actual NodeList entry guards and full keep-alive method, no socket production."""
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class NodeListVisibility(unittest.TestCase):
    def test_actual_guards_keepalive_and_atomic_publication(self):
        source = (ROOT / "libraries/networking/src/NodeList.cpp").read_text()
        header = (ROOT / "libraries/networking/src/NodeList.h").read_text()
        setter = re.search(r"    void setClientTransportVisibility\(bool foreground\) \{[^}]+\}", header).group()
        field = re.search(r"    std::atomic<bool> _clientTransportSuspended[^;]+;", header).group()
        names = ("sendDomainServerCheckIn", "handleICEConnectionToDomainServer", "pingPunchForDomainServer",
                 "pingPunchForInactiveNode", "startNodeHolePunch")
        methods = []
        for name in names:
            # Compile the actual complete entry guard; intentionally substitute
            # the unchanged large network body with a boundary counter.
            prefix = re.search(r"void NodeList::" + name + r"\([^\n]*\) \{\n"
                               r"    if \(_clientTransportSuspended.load\(std::memory_order_acquire\)\) \{ return; \}", source)
            self.assertIsNotNone(prefix, name)
            methods.append(prefix.group() + "\n    ++afterFence;\n}\n")
        methods.append("void NodeList::sendKeepAlivePings() {" + source.split(
            "void NodeList::sendKeepAlivePings() {", 1)[1].split(
            "\nbool NodeList::sockAddrBelongsToDomainOrNode", 1)[0])
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-node-visibility-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "node-visibility-state.inc").write_text(setter + "\n" + field)
            (temporary / "node-visibility-methods.inc").write_text("\n".join(methods))
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(temporary),
                            str(pathlib.Path(__file__).with_name("nodelist-visibility-test.cpp")), "-o", str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary)], check=True, timeout=5)

    def test_actual_startup_installs_both_receivers_before_seed(self):
        setup = (ROOT / "interface/src/Application_Setup.cpp").read_text()
        start = setup.index("DependencyManager::set<AddressManager>();")
        seed = setup.index("overte::lifecycle::observeQtVisibility(", start)
        self.assertLess(setup.index("DependencyManager::set<NodeList>(", start), seed)
        header = (ROOT / "libraries/networking/src/NodeList.h").read_text()
        self.assertLess(header.index("void setClientTransportVisibility("), header.index("public slots:"))


if __name__ == "__main__":
    unittest.main()
