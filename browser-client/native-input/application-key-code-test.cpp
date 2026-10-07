// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include "application-key-route.h"
#include <cstdio>
#include <cassert>
int main() {
    using namespace BrowserApplicationKey;
    for (int value=32;value<=126;++value) {
        Key key;const auto text=QString(QChar(value));assert(decode(text,key));
        assert(key.text==text && key.code==QChar(value).toUpper().unicode());
    }
    struct Expected { const char* name; int code; const char* text; };
    const Expected expected[] = {
        {"Backspace",Qt::Key_Backspace,"\b"},{"Tab",Qt::Key_Tab,"\t"},{"Enter",Qt::Key_Return,"\r"},
        {"Delete",Qt::Key_Delete,"\x7f"},{"Escape",Qt::Key_Escape,"\x1b"},
        {"ArrowLeft",Qt::Key_Left,""},{"ArrowRight",Qt::Key_Right,""},
        {"ArrowUp",Qt::Key_Up,""},{"ArrowDown",Qt::Key_Down,""},
        {"F1",Qt::Key_F1,""},{"F12",Qt::Key_F12,""},{"Home",Qt::Key_Home,""},
        {"End",Qt::Key_End,""},{"Insert",Qt::Key_Insert,""},{"PageUp",Qt::Key_PageUp,""},{"PageDown",Qt::Key_PageDown,""}
    };
    for(const auto& value: expected) {Key key;assert(decode(QLatin1String(value.name),key));assert(key.code==value.code&&key.text==QLatin1String(value.text));}
    for(const auto& value: {QString(),QString("ctrl+x"),QString("ArrowLeft "),QString("F13"),QString("\n"),QString(QChar(0)),QString(QChar(127)),QString(QChar(0xe9)),QString::fromUtf8("😀")}){Key key;assert(!decode(value,key));}
    Target target;assert(!nativeTarget(target));
    assert(!click(nullptr,nullptr,nullptr,"x",0));
    assert(!click(nullptr,nullptr,nullptr,"x",Qt::KeypadModifier));
    std::puts("{\"completed\":true,\"asciiCases\":95,\"specialCases\":16,\"refusalCases\":12,\"guiApplicationCreated\":false}");
    return 0;
}
