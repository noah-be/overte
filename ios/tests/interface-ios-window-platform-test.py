#!/usr/bin/env python3
"""Contract preventing desktop utility windows from opening on iOS."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APPLICATION_UI = (ROOT / "interface/src/Application_UI.cpp").read_text()
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text()
APPLICATION_SETUP = (ROOT / "interface/src/Application_Setup.cpp").read_text()
APPLICATION_GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
INTERFACE_CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
LOG_DIALOG = (ROOT / "interface/src/ui/LogDialog.cpp").read_text()
BASE_LOG_DIALOG = (ROOT / "interface/src/ui/BaseLogDialog.cpp").read_text()
MENU = (ROOT / "interface/src/Menu.cpp").read_text()
JS_CONSOLE = (ROOT / "interface/src/ui/StandAloneJSConsole.cpp").read_text()
DIALOGS_MANAGER = (ROOT / "interface/src/ui/DialogsManager.cpp").read_text()
DOMAIN_DIALOG = (ROOT / "interface/src/ui/DomainConnectionDialog.cpp").read_text()
OCTREE_DIALOG = (ROOT / "interface/src/ui/OctreeStatsDialog.cpp").read_text()
LOD_DIALOG = (ROOT / "interface/src/ui/LodToolsDialog.cpp").read_text()
LOD_MANAGER = (ROOT / "interface/src/LODManager.cpp").read_text()
HMD_TOOLS = (ROOT / "interface/src/ui/HMDToolsDialog.cpp").read_text()
TESTING_DIALOG = (ROOT / "interface/src/ui/TestingDialog.cpp").read_text()


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
require("// Developer > Log\n#if !defined(Q_OS_IOS)" in MENU and
        "qApp, SLOT(toggleLogDialog())" in MENU,
        "desktop LogDialog action remains in the iOS developer menu")
require("void Application::toggleEntityScriptServerLogDialog() {\n"
        "#if !defined(Q_OS_IOS)" in APPLICATION_UI,
        "desktop Entity Script Server log dialog remains reachable on iOS")
require("// Developer > Scripting > Entity Script Server Log\n"
        "#if !defined(Q_OS_IOS)" in MENU,
        "nonfunctional desktop log action remains in the iOS developer menu")
require("BaseLogDialog::BaseLogDialog(QWidget* parent) : QDialog(parent, Qt::Window)" in BASE_LOG_DIALOG and
        "setMinimumWidth(MINIMAL_WIDTH);" in BASE_LOG_DIALOG,
        "Entity Script Server log is no longer demonstrably a desktop utility window")
for desktop_log_source in (
        "BaseLogDialog.cpp", "BaseLogDialog.h",
        "EntityScriptServerLogDialog.cpp", "EntityScriptServerLogDialog.h",
        "LogDialog.cpp", "LogDialog.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/ui/{desktop_log_source}"' in INTERFACE_CMAKE,
            f"{desktop_log_source} remains in the iOS compile/MOC graph")
require("#if !defined(Q_OS_IOS)\n#include <ui/EntityScriptServerLogDialog.h>\n#endif" in APPLICATION_UI and
        "#if !defined(Q_OS_IOS)\n#include <ui/LogDialog.h>\n#endif" in APPLICATION_UI,
        "desktop log dialog headers remain in the iOS Application UI graph")
require("DependencyManager::set<EntityScriptServerLogClient>();" in APPLICATION_SETUP,
        "backend Entity Script Server log client was incorrectly removed with desktop dialogs")
require("void StandAloneJSConsole::toggleConsole()  {\n#if !defined(Q_OS_IOS)" in JS_CONSOLE,
        "stand-alone desktop JavaScript console remains reachable on iOS")
require("// Developer > Scripting > Console...\n#if !defined(Q_OS_IOS)" in MENU,
        "stand-alone JavaScript console action remains in the iOS menu")
require("new QDialog(mainWindow, Qt::WindowStaysOnTopHint)" in JS_CONSOLE and
        "dialog->resize(QSize(CONSOLE_WIDTH, CONSOLE_HEIGHT));" in JS_CONSOLE,
        "stand-alone JavaScript console is no longer demonstrably a desktop utility window")
require(INTERFACE_CMAKE.count("src/ui/StandAloneJSConsole") == 2,
        "stand-alone JavaScript console sources are not deterministically removed on iOS")
require("#if !defined(Q_OS_IOS)\n#include <ui/StandAloneJSConsole.h>\n#endif" in APPLICATION_SETUP and
        "#if !defined(Q_OS_IOS)\n    DependencyManager::set<StandAloneJSConsole>();\n#endif" in APPLICATION_SETUP,
        "stand-alone console singleton remains initialized on iOS")
require("#if !defined(Q_OS_IOS)\n#include <ui/StandAloneJSConsole.h>\n#endif" in APPLICATION and
        "#if !defined(Q_OS_IOS)\n        DependencyManager::destroy<StandAloneJSConsole>();\n#endif" in APPLICATION,
        "stand-alone console shutdown dependency remains on iOS")
require("#if !defined(Q_OS_IOS)\n#include \"ui/StandAloneJSConsole.h\"\n#endif" in MENU,
        "stand-alone console header remains in the iOS menu graph")
require("void DialogsManager::showDomainConnectionDialog() {\n#if !defined(Q_OS_IOS)" in DIALOGS_MANAGER,
        "desktop Domain Connection table dialog remains reachable on iOS")
require("QDialog(parent, Qt::Window | Qt::WindowCloseButtonHint)" in DOMAIN_DIALOG and
        "timeTable->setMinimumSize(tableWidth, tableHeight);" in DOMAIN_DIALOG,
        "Domain Connection dialog is no longer demonstrably a desktop utility window")
require('tablet->pushOntoStack("hifi/dialogs/TabletDCDialog.qml");' in APPLICATION_UI,
        "mobile-friendly Domain Connection timing surface changed")
require("#if !defined(Q_OS_IOS)\n#include \"DomainConnectionDialog.h\"\n#endif" in DIALOGS_MANAGER,
        "desktop Domain Connection dialog header remains in the iOS manager graph")
for domain_dialog_source in ("DomainConnectionDialog.cpp", "DomainConnectionDialog.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/ui/{domain_dialog_source}"' in INTERFACE_CMAKE,
            f"{domain_dialog_source} remains in the iOS compile/MOC graph")
require("DependencyManager::set<DomainConnectionModel>();" in APPLICATION_SETUP,
        "tablet Domain Connection model was incorrectly removed with desktop dialog")
require("void DialogsManager::octreeStatsDetails() {\n#if !defined(Q_OS_IOS)" in DIALOGS_MANAGER,
        "desktop Octree statistics dialog remains reachable on iOS")
require("QDialog(parent, Qt::Window | Qt::WindowCloseButtonHint | Qt::WindowStaysOnTopHint)" in OCTREE_DIALOG and
        "const int STATS_LABEL_WIDTH = 600;" in OCTREE_DIALOG,
        "Octree statistics dialog is no longer demonstrably a desktop utility window")
require('tablet->pushOntoStack("hifi/dialogs/TabletEntityStatistics.qml");' in APPLICATION_UI,
        "mobile-friendly Entity statistics surface changed")
for octree_dialog_source in ("OctreeStatsDialog.cpp", "OctreeStatsDialog.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/ui/{octree_dialog_source}"' in INTERFACE_CMAKE,
            f"{octree_dialog_source} remains in the iOS compile/MOC graph")
require("#if !defined(Q_OS_IOS)\n#include <ui/OctreeStatsDialog.h>\n#endif" in APPLICATION_UI and
        "#if !defined(Q_OS_IOS)\n    QPointer<OctreeStatsDialog>" in APPLICATION_UI,
        "desktop Octree dialog per-frame update remains in the iOS UI graph")
require("#if !defined(Q_OS_IOS)\n#include \"OctreeStatsDialog.h\"\n#endif" in DIALOGS_MANAGER,
        "desktop Octree dialog header remains in the iOS manager graph")
require("#if !defined(Q_OS_IOS)\n#include \"OctreeStatsDialog.h\"\n#endif" in HMD_TOOLS and
        "#if !defined(Q_OS_IOS)\n    if (dialogsManager->getOctreeStatsDialog())" in HMD_TOOLS,
        "desktop HMD window watcher retains Octree dialog on iOS")
for hmd_dialog_source in ("HMDToolsDialog.cpp", "HMDToolsDialog.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/ui/{hmd_dialog_source}"' in INTERFACE_CMAKE,
            f"{hmd_dialog_source} remains in the iOS compile/MOC graph")
require("#if !defined(Q_OS_IOS)\n#include \"HMDToolsDialog.h\"\n#else\n"
        "class HMDToolsDialog;\n#endif" in (ROOT / "interface/src/ui/DialogsManager.h").read_text(),
        "desktop HMD dialog type remains included by the iOS manager header")
require("void DialogsManager::hmdTools(bool showTools) {\n#if !defined(Q_OS_IOS)" in DIALOGS_MANAGER and
        "#else\n    Q_UNUSED(showTools)\n#endif" in DIALOGS_MANAGER,
        "desktop HMD tools window remains reachable on iOS")
for testing_dialog_source in ("TestingDialog.cpp", "TestingDialog.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/ui/{testing_dialog_source}"' in INTERFACE_CMAKE,
            f"{testing_dialog_source} remains in the iOS compile/MOC graph")
require("#if !defined(Q_OS_IOS)\n#include \"TestingDialog.h\"\n#else\n"
        "class TestingDialog;\n#endif" in (ROOT / "interface/src/ui/DialogsManager.h").read_text(),
        "desktop TestingDialog type remains included by the iOS manager header")
require("Qt::WindowStaysOnTopHint" in TESTING_DIALOG and
        "_console(new JSConsole(this))" in TESTING_DIALOG,
        "TestingDialog is no longer demonstrably a desktop test-console window")
require("maybeCreateDialog(_testingDialog)" not in DIALOGS_MANAGER,
        "TestingDialog gained a manager creation path and must be re-audited")
require("void DialogsManager::lodTools() {\n#if !defined(Q_OS_IOS)" in DIALOGS_MANAGER,
        "desktop LOD tools dialog remains reachable on iOS")
require("QDialog(parent, Qt::Window | Qt::WindowCloseButtonHint | Qt::WindowStaysOnTopHint)" in LOD_DIALOG and
        "const int SLIDER_WIDTH = 300;" in LOD_DIALOG,
        "LOD tools dialog is no longer demonstrably a desktop utility window")
require('tablet->pushOntoStack("hifi/dialogs/TabletLODTools.qml");' in APPLICATION_UI,
        "mobile-friendly LOD tools surface changed")
for lod_dialog_source in ("LodToolsDialog.cpp", "LodToolsDialog.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/ui/{lod_dialog_source}"' in INTERFACE_CMAKE,
            f"{lod_dialog_source} remains in the iOS compile/MOC graph")
require("#if !defined(Q_OS_IOS)\n#include \"ui/LodToolsDialog.h\"\n#endif" in LOD_MANAGER and
        "#if !defined(Q_OS_IOS)\n        auto lodToolsDialog" in LOD_MANAGER,
        "desktop LOD tools refresh remains in the iOS manager graph")
require("#if !defined(Q_OS_IOS)\n#include \"LodToolsDialog.h\"\n#endif" in HMD_TOOLS and
        "#if !defined(Q_OS_IOS)\n    if (dialogsManager->getLodToolsDialog())" in HMD_TOOLS,
        "desktop HMD window watcher retains LOD dialog on iOS")
require("#if !defined(ANDROID_APP_PHONE_INTERFACE) && !defined(Q_OS_IOS)\n"
        "        bool buildCanUpdate" in APPLICATION_SETUP,
        "desktop AutoUpdater startup remains reachable on iOS")
require("DependencyManager::set<AutoUpdater>()" in APPLICATION_SETUP and
        "&AutoUpdater::newVersionIsAvailable" in APPLICATION_SETUP,
        "desktop updater behavior changed on supported platforms")
require("#if !defined(Q_OS_IOS)\n#include <ui/UpdateDialog.h>\n#endif" in APPLICATION_GRAPHICS and
        "#if !defined(Q_OS_IOS)\n    UpdateDialog::registerType();\n#endif" in APPLICATION_GRAPHICS,
        "unavailable desktop UpdateDialog remains registered on iOS")
require("#if !defined(Q_OS_IOS)\n#include \"UpdateDialog.h\"\n#endif" in DIALOGS_MANAGER and
        "void DialogsManager::showUpdateDialog() {\n#if !defined(Q_OS_IOS)\n"
        "    UpdateDialog::show();" in DIALOGS_MANAGER,
        "desktop UpdateDialog manager entry remains reachable on iOS")
require("set(INTERFACE_AUTO_UPDATER_LIBRARY auto-updater)" in INTERFACE_CMAKE and
        '"${CMAKE_CURRENT_SOURCE_DIR}/src/ui/UpdateDialog.cpp"' in INTERFACE_CMAKE and
        '"${CMAKE_CURRENT_SOURCE_DIR}/src/ui/UpdateDialog.h"' in INTERFACE_CMAKE,
        "desktop UpdateDialog sources remain in the iOS compile/moc graph")
require('set(INTERFACE_AUTO_UPDATER_LIBRARY "")' in INTERFACE_CMAKE and
        "qml ${INTERFACE_AUTO_UPDATER_LIBRARY} midi" in INTERFACE_CMAKE,
        "unused desktop auto-updater remains linked into the iOS Interface")

print("iOS window platform contract valid: desktop log/console windows preserved and mobile-excluded")
