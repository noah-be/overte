#!/usr/bin/env python3
"""Contract preventing desktop utility windows from opening on iOS."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APPLICATION_UI = (ROOT / "interface/src/Application_UI.cpp").read_text()
LOG_DIALOG = (ROOT / "interface/src/ui/LogDialog.cpp").read_text()


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

print("iOS window platform contract valid: desktop LogDialog preserved and mobile-excluded")
