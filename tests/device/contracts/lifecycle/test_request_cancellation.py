#!/usr/bin/env python3
import pathlib
import os
import re
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

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
        session_field = re.findall(r"^\s*(QUuid _sessionID\s*\{[^\n]+\};)", header, re.MULTILINE)
        self.assertEqual(len(session_field), 1, "Actual session owner must retain its reviewed QUuid type")
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
            (temporary / "account-session-field.inc").write_text(session_field[0] + "\n")
            (temporary / "account-send-request.inc").write_text(
                block(source, "QNetworkRequest AccountManager::createRequest(") + "\n" + method)
            (temporary / "address-request-methods.inc").write_text(address_methods)
            moc = temporary / "request-cancellation-test.moc"
            subprocess.run([str(pathlib.Path(libexec) / "moc"), str(driver), "-o", str(moc)], check=True, timeout=15)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(ROOT), "-I", str(temporary),
                            str(driver), "-o", str(binary), *flags], check=True, timeout=45)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_generic_and_oauth_managers_enforce_credential_transport(self):
        major = os.environ.get("OVERTE_CREDENTIAL_QT_MAJOR", "6")
        self.assertIn(major, ("5", "6"))
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", *["Qt" + major + module
                for module in ("Core", "Network", "Qml")]], text=True))
        variable = "host_bins" if major == "5" else "libexecdir"
        libexec = subprocess.check_output(
            ["pkg-config", "--variable=" + variable, "Qt" + major + "Core"], text=True).strip()
        sysroot = os.environ.get("PKG_CONFIG_SYSROOT_DIR", "")
        if sysroot and not pathlib.Path(libexec, "moc").is_file():
            libexec = str(pathlib.Path(sysroot) / libexec.lstrip("/"))
        driver = pathlib.Path(__file__).with_name("credential-transport-test.cpp")
        with tempfile.TemporaryDirectory(prefix="overte-credential-transport-") as temporary:
            scratch = pathlib.Path(temporary)
            for name in ("NetworkAccessManager", "OAuthNetworkAccessManager"):
                relative = "libraries/networking/src/" + name + ".cpp"
                baseline = os.environ.get("OVERTE_CREDENTIAL_MANAGER_BASELINE")
                source = (subprocess.check_output(["git", "-C", str(ROOT), "show",
                    baseline + ":" + relative], text=True) if baseline else (ROOT / relative).read_text())
                # Retain the entire production implementation; replace only its
                # dependency includes with the explicit boundaries in the driver.
                methods = "\n".join(line for line in source.splitlines()
                                    if not line.startswith("#include"))
                (scratch / (name + ".inc")).write_text(methods)
            filters = (ROOT / "libraries/ui/src/ui/types/RequestFilters.cpp").read_text()
            (scratch / "request-filter-auth.inc").write_text(
                block(filters, "    bool isAuthableMetaverseURL("))
            subprocess.run([str(pathlib.Path(libexec) / "moc"),
                str(ROOT / "libraries/networking/src/NetworkAccessManager.h"),
                "-o", str(scratch / "network.moc.cpp")], check=True, timeout=15)
            binary = scratch / "credential-test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-I", str(ROOT), "-I", str(scratch),
                str(driver), str(scratch / "network.moc.cpp"), "-o", str(binary), *flags],
                check=True, timeout=45)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary)],
                check=True, timeout=10)

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
            entry = body.split("{", 1)[1]
            self.assertIn("QPointer<QNetworkReply> guardedReply(" + argument + ");", entry)
            self.assertIn("const auto lookup = _lookupRequests.snapshot();", entry)
            self.assertIn("guardedReply && lookup.current() &&", entry)
            self.assertIn("overte::network::replyCurrent(guardedReply.data())", entry)
            self.assertIn("if (!current()) { return; }", entry)
            self.assertLess(entry.index("if (!current()) { return; }"),
                            entry.index("QJsonObject" if method == "handleAPIResponse" else "qCDebug"))
        self.assertIn("if (!_lookupForeground) { return false; }", address)
        self.assertIn("trigger != UserInput && trigger != Back && trigger != Forward && trigger != Suggestions", address)


if __name__ == "__main__": unittest.main()
