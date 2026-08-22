#!/usr/bin/env python3
"""Ensure the vk target does not regress to Qt private/qpa APIs."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
vk_root = ROOT / "libraries/vk"
cmake = (vk_root / "CMakeLists.txt").read_text(encoding="utf-8")

if "GuiPrivate" in cmake:
    raise SystemExit("vk target still links Qt GuiPrivate")
if "overte_find_qt(COMPONENTS Core Gui QUIET REQUIRED)" not in cmake:
    raise SystemExit("vk target public Qt Core/Gui requirement is missing")

private_tokens = ("<qpa/", "QtGui/private/", "QtCore/private/", "QPlatformNativeInterface")
for source in (vk_root / "src").rglob("*"):
    if source.suffix not in (".h", ".cpp", ".mm"):
        continue
    text = source.read_text(encoding="utf-8", errors="replace")
    for token in private_tokens:
        if token in text:
            raise SystemExit(f"{source.relative_to(ROOT)} still uses private Qt token {token!r}")

window = (vk_root / "src/vk/VKWindow.cpp").read_text(encoding="utf-8")
x11_include = "#include <QtX11Extras/QX11Info>"
position = window.index(x11_include)
guard = window.rfind("#if !defined(WIN32) && !defined(Q_OS_IOS)", 0, position)
end = window.find("#endif", position)
if guard < 0 or end < 0:
    raise SystemExit("VKWindow X11 include is not excluded from iOS")

print("vk Qt API contract valid: public Core/Gui only; qpa absent; X11 excluded on iOS")
