#!/usr/bin/env python3
"""Execute iOS startup policy and window ownership with host Qt (not native acceptance)."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text()


def preprocess(source, *defines):
    return subprocess.run(
        ['c++', '-E', '-P', '-x', 'c++', *['-D' + d for d in defines], '-'],
        input=source, text=True, capture_output=True, check=True, timeout=15).stdout


# Compile the production iOS readiness dispatch, retaining the old non-iOS
# workaround branch. The Qt callback must be deferred and lifetime-bound.
offscreen = read('libraries/ui/src/OffscreenUi.cpp')
focus_start = offscreen.index('#if !defined(Q_OS_IOS)\n        auto keyboardFocus')
focus_end = offscreen.index('\n    });', focus_start)
focus = offscreen[focus_start:focus_end]
ios_focus = preprocess(focus, 'Q_OS_IOS')
assert 'KeyboardFocusHack' not in ios_focus
assert 'new KeyboardFocusHack()' in preprocess(focus)
assert ios_focus.index('emit desktopReady();') < ios_focus.index('QTimer::singleShot')
ready_dispatch = ios_focus.split('emit desktopReady();', 1)[1]
app = read('interface/src/Application.cpp')
setup = read('interface/src/Application_Setup.cpp')
ui = read('interface/src/Application_UI.cpp')
menu = read('interface/src/Menu.cpp').split('// Developer > Show Statistics', 1)[1].split(
    '// Developer > Show Animation Statistics', 1)[0]
defaults = {}
for variant, defines in [('release', ['Q_OS_IOS']),
                         ('debug', ['Q_OS_IOS', 'OVERTE_IOS_DEBUG_STATS']),
                         ('pico', ['ANDROID_APP_PICO_INTERFACE']), ('desktop', [])]:
    defaults[variant] = preprocess(menu, *defines)

init = app.split('    _vkWindow(new VKWindow()),', 1)[1].split(
    '    // Menu needs', 1)[0].rsplit('#endif', 1)[0]
init = preprocess(init, 'Q_OS_IOS').rstrip().rstrip(',')
container = setup.split('    _primaryWidget = new VKCanvas();', 1)[1].split(
    '    _vkWindowWrapper->setFocusProxy', 1)[0]
container = preprocess(container, 'Q_OS_IOS')
policy = ui[ui.index('    const bool statsVisible = iosRuntimeDiagnosticBool('):]
policy = policy.split('    menu->setIsOptionChecked', 1)[0]
getter = read('libraries/shared/src/shared/IOSRuntimeLogging.h').split(
    'inline bool iosRuntimeDiagnosticBool(', 1)[1].split('\n}', 1)[0]
getter = 'bool iosRuntimeDiagnosticBool(' + getter + '\n}'

cpp = r'''
#include <QApplication>
#include <QMainWindow>
#include <QWindow>
#include <QJsonObject>
#include <QTimer>
#include <cassert>
#include <iostream>
using MainWindow = QMainWindow;
struct Ready : QObject {
    int& count;
    Ready(int& value) : count(value) {}
    void keyboardFocusActive() { ++count; }
    void dispatch() { READY_DISPATCH }
};
struct Host {
    QWindow* _vkWindow;
    QWidget* _vkWindowWrapper;
    MainWindow* _window;
    Host() : _vkWindow(new QWindow()), INITIALIZERS {
        CONTAINER
        _window->setCentralWidget(_vkWindowWrapper);
    }
    ~Host() { delete _window; }
};
namespace MenuOption { constexpr int Stats = 1; }
QJsonObject config;
QJsonObject iosRuntimeDiagnosticConfig() { return config; }
GETTER
struct Menu { bool checked; bool isOptionChecked(int) { return checked; } };
bool actionDefault;
int developerMenu = 0;
void addCheckableActionToQMenuAndActionHash(int, int, int, bool value) { actionDefault = value; }
bool releaseDefault() { RELEASE return actionDefault; }
bool debugDefault() { DEBUG_DEFAULT return actionDefault; }
bool picoDefault() { PICO return actionDefault; }
bool desktopDefault() { DESKTOP return actionDefault; }
void check(bool checked, bool expectedVisible, bool expectedExpanded) {
    Menu storage{checked}; auto menu = &storage;
    POLICY
    assert(statsVisible == expectedVisible);
    assert(statsExpanded == expectedExpanded);
}
int main(int argc, char** argv) {
    QApplication application(argc, argv);
    int readyCount = 0;
    const auto windowCount = QGuiApplication::allWindows().size();
    { Ready ready(readyCount); ready.dispatch(); assert(readyCount == 0);
      application.processEvents(); assert(readyCount == 1);
      application.processEvents(); assert(readyCount == 1); }
    auto cancelled = new Ready(readyCount); cancelled->dispatch(); delete cancelled;
    application.processEvents(); assert(readyCount == 1);
    assert(QGuiApplication::allWindows().size() == windowCount);
    assert(!releaseDefault() && debugDefault() && !picoDefault() && desktopDefault());
    check(releaseDefault(), false, false);
    check(debugDefault(), true, false);
    check(true, true, false); // retained user setting
    config = {{"statsOverlay", true}, {"statsOverlayExpanded", true}};
    check(false, true, true); // explicit diagnostic opt-in
    config = {{"statsOverlay", false}};
    check(true, false, false); // explicit opt-out, including Debug
    config = {{"statsOverlay", "true"}, {"statsOverlayExpanded", 1}};
    check(false, false, false); // invalid types cannot opt in
    check(true, true, false);
    {
        // Reproduce the original two-container hierarchy independently of Vulkan.
        auto render = new QWindow();
        auto orphan = QWidget::createWindowContainer(render);
        auto main = new MainWindow(orphan);
        main->setCentralWidget(QWidget::createWindowContainer(render));
        assert(main->parentWidget() == orphan);
        assert(QApplication::topLevelWidgets().size() == 2);
        delete orphan;
    }
    assert(QApplication::topLevelWidgets().isEmpty());
    {
        Host host;
        assert(host._window->parentWidget() == nullptr);
        assert(host._vkWindowWrapper->parentWidget() == host._window);
        assert(QApplication::topLevelWidgets().size() == 1);
        host._window->showFullScreen();
        application.processEvents();
        assert(host._window->isVisible());
        assert(host._window->centralWidget() == host._vkWindowWrapper);
        assert(host._vkWindowWrapper->isVisible());
    }
    assert(QApplication::topLevelWidgets().isEmpty());
    std::cout << "PASS: production stats defaults/overrides; old extra window reproduced; single owned visible container and cleanup; deferred/lifetime-bound iOS focus readiness without extra window\n";
}
'''
for key, value in {'READY_DISPATCH': ready_dispatch, 'INITIALIZERS': init, 'CONTAINER': container, 'GETTER': getter,
                   'POLICY': policy, 'RELEASE': defaults['release'],
                   'DEBUG_DEFAULT': defaults['debug'], 'PICO': defaults['pico'],
                   'DESKTOP': defaults['desktop']}.items():
    cpp = cpp.replace(key, value)

with tempfile.TemporaryDirectory(prefix='ios-startup-policy-') as directory:
    tmp = Path(directory)
    (tmp / 'test.cpp').write_text(cpp)
    flags = shlex.split(subprocess.check_output(
        ['pkg-config', '--cflags', '--libs', 'Qt6Widgets'], text=True))
    subprocess.run(['c++', '-std=c++17', '-fPIC', str(tmp / 'test.cpp'),
                    '-o', str(tmp / 'test'), *flags], check=True, timeout=45)
    subprocess.run([str(tmp / 'test')], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                   check=True, timeout=20)
