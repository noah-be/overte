#!/usr/bin/env python3
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class RequestCancellation(unittest.TestCase):
    def test_startup_lookup_hook_compiles_in_free_function_scope(self):
        setup = (ROOT / "interface/src/Application_Setup.cpp").read_text()
        essentials = setup.split("bool setupEssentials(", 1)[1].split("\n}", 1)[0]
        hook = next(line.strip() for line in essentials.splitlines()
                    if "observeQtVisibility(" in line)
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "Qt6Gui"], text=True))
        source = """#include <QGuiApplication>
#include "interface/src/ApplicationLifecycle.h"
class AddressManager { public: void setClientLookupVisibility(bool); };
class DependencyManager { public: template<class T> static T* get(); };
void setupEssentialsScope() {
""" + hook + "\n}\n"
        result = subprocess.run(["c++", "-std=c++17", "-fPIC", "-fsyntax-only", "-I", str(ROOT),
                                 "-x", "c++", "-", *flags], input=source,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_account_request_and_real_qt_abort(self):
        source = (ROOT / "libraries/networking/src/AccountManager.cpp").read_text()
        header = (ROOT / "libraries/networking/src/AccountManager.h").read_text()
        method = "void AccountManager::sendRequest(" + source.split("void AccountManager::sendRequest(", 1)[1].split("\nbool writeAccountMapToFile", 1)[0]
        callback = "class JSONCallbackParameters {" + header.split("class JSONCallbackParameters {", 1)[1].split("\n};", 1)[0] + "\n};\n"
        constructor = "JSONCallbackParameters::JSONCallbackParameters(" + source.split("JSONCallbackParameters::JSONCallbackParameters(", 1)[1].split("\n}", 1)[0] + "\n}\n"
        address = (ROOT / "libraries/networking/src/AddressManager.cpp").read_text()
        address_methods = "void AddressManager::setClientLookupVisibility(" + address.split("void AddressManager::setClientLookupVisibility(", 1)[1].split("\nbool AddressManager::handleUrl", 1)[0]
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Network"], text=True))
        libexec = subprocess.check_output(["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()
        driver = pathlib.Path(__file__).with_name("request-cancellation-test.cpp")
        with tempfile.TemporaryDirectory(prefix="sh005-http-cancel-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "callback-parameters.inc").write_text(callback + constructor)
            (temporary / "account-send-request.inc").write_text(method)
            (temporary / "address-request-methods.inc").write_text(address_methods)
            moc = temporary / "request-cancellation-test.moc"
            subprocess.run([str(pathlib.Path(libexec) / "moc"), str(driver), "-o", str(moc)], check=True, timeout=15)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(ROOT), "-I", str(temporary),
                            str(driver), "-o", str(binary), *flags], check=True, timeout=45)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_shared_entry_and_late_reply_guards(self):
        events = (ROOT / "interface/src/Application_Events.cpp").read_text()
        setup = (ROOT / "interface/src/Application_Setup.cpp").read_text()
        address = (ROOT / "libraries/networking/src/AddressManager.cpp").read_text()
        header = (ROOT / "libraries/networking/src/AddressManager.h").read_text()
        self.assertLess(header.index("void setClientLookupVisibility("), header.index("public slots:"))
        self.assertIn("observeQtVisibility(state == Qt::ApplicationActive)", events)
        self.assertIn("setClientLookupVisibility(effective)", events)
        self.assertIn("observeQtVisibility(QGuiApplication::applicationState() == Qt::ApplicationActive)", setup)
        self.assertIn("callbackParams.requestTicket = _lookupRequests.next()", address)
        for method, argument in (("handleAPIResponse", "requestReply"), ("handleAPIError", "errorReply")):
            body = address.split("void AddressManager::" + method + "(", 1)[1].split("\n}", 1)[0]
            self.assertTrue(body.split("{", 1)[1].lstrip().startswith("if (!overte::network::replyCurrent(" + argument))
        self.assertIn("if (!_lookupForeground) { return false; }", address)
        self.assertIn("trigger != UserInput && trigger != Back && trigger != Forward && trigger != Suggestions", address)


if __name__ == "__main__": unittest.main()
