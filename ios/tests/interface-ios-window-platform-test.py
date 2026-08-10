#!/usr/bin/env python3
"""Contract preventing desktop utility windows from opening on iOS."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APPLICATION_UI = (ROOT / "interface/src/Application_UI.cpp").read_text()
LOG_DIALOG = (ROOT / "interface/src/ui/LogDialog.cpp").read_text()
BASE_LOG_DIALOG = (ROOT / "interface/src/ui/BaseLogDialog.cpp").read_text()
MENU = (ROOT / "interface/src/Menu.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("void Application::toggleLogDialog() {\n"
        "#if !defined(ANDROID_APP_QUEST_INTERFACE) && !defined(Q_OS_IOS)" in APPLICATION_UI,
        "desktop LogDialog toggle remains reachable on iOS")
require("_logDialog = new LogDialog(nullptr, getLogger());" in APPLICATION_UI,
        "desktop LogDialog behavior changed for supported platforms")
require('new QPushButton(QIcon(":/styles/txt-file.svg"), "Reveal log file", this)' in LOG_DIALOG,
        "LogDialog is no longer demonstrably a desktop file/window utility")
require("Qt::WindowFlags flags = _logDialog->windowFlags() | Qt::Tool;" in APPLICATION_UI,
        "desktop window-on-top behavior changed")
require("void Application::toggleEntityScriptServerLogDialog() {\n"
        "#if !defined(Q_OS_IOS)" in APPLICATION_UI,
        "desktop Entity Script Server log dialog remains reachable on iOS")
require("// Developer > Scripting > Entity Script Server Log\n"
        "#if !defined(Q_OS_IOS)" in MENU,
        "nonfunctional desktop log action remains in the iOS developer menu")
require("BaseLogDialog::BaseLogDialog(QWidget* parent) : QDialog(parent, Qt::Window)" in BASE_LOG_DIALOG and
        "setMinimumWidth(MINIMAL_WIDTH);" in BASE_LOG_DIALOG,
        "Entity Script Server log is no longer demonstrably a desktop utility window")

print("iOS window platform contract valid: desktop log dialogs preserved and mobile-excluded")
