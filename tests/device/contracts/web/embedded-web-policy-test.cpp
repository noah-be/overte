// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../../../libraries/shared/src/EmbeddedWebPolicy.h"
#include <QCoreApplication>
#include <QFile>
#include <QTemporaryDir>
#include <cassert>
#include <iostream>

using overte::web::EmbeddedWebSession;
using overte::web::Surface;

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    EmbeddedWebSession session;
    const QUrl original("https://world.example/app.html");
    auto generation = session.open(original, Surface::WorldEntity, "entity-one");
    assert(generation != 0 && session.active());
    assert(session.allowsNavigation(generation, QUrl("https://other.example/login"), true, "POST"));
    assert(session.allowsNavigation(generation, QUrl("https://other.example/frame"), false, "GET"));
    assert(!session.allowsNavigation(generation, original, true, "CONNECT"));
    assert(session.allowsBridge(generation, QUrl("https://world.example:443/app.html#anchor"), true, 1));
    assert(session.allowsBridge(generation, original, true, EmbeddedWebSession::MAX_BRIDGE_BYTES));
    assert(!session.allowsBridge(generation, original, true, EmbeddedWebSession::MAX_BRIDGE_BYTES + 1));
    assert(!session.allowsBridge(generation, original, true, 0));
    assert(!session.allowsBridge(generation, original, false, 100));
    assert(!session.allowsBridge(generation, QUrl("http://world.example/app.html"), true, 100));
    assert(!session.allowsBridge(generation, QUrl("https://world.example:444/app.html"), true, 100));
    assert(!session.allowsBridge(generation, QUrl("https://other.example/app.html"), true, 100));
    assert(session.allowsScriptURL(QUrl("https://source.example/entity.js")));

    for (const auto* rejected : {"javascript:alert(1)", "data:text/html,hello", "file:///private/doc",
                                "content://private/doc", "qrc:/scripts/test.js", "https://user:secret@example.com/",
                                "https://example.com/%0a", "https://example.com/%00", "/relative.html"}) {
        assert(!session.allowsNavigation(generation, QUrl(rejected), true, "GET"));
        assert(!session.allowsScriptURL(QUrl(rejected)));
    }

    assert(session.setForeground(false));
    assert(!session.active() && !session.allowsBridge(generation, original, true, 10));
    assert(!session.allowsScriptURL(QUrl("https://source.example/entity.js")));
    assert(session.setForeground(true));
    assert(session.active() && session.generation() != generation);
    assert(!session.allowsBridge(generation, original, true, 10));
    generation = session.generation();
    assert(session.allowsBridge(generation, original, true, 10));
    assert(session.setVisible(false));
    assert(!session.active());
    assert(session.setVisible(true));
    assert(session.active() && !session.allowsBridge(generation, original, true, 10));
    generation = session.open(original, Surface::Tablet, "tablet-one");
    auto replacement = session.open(original, Surface::Tablet, "tablet-two");
    assert(replacement != generation);
    assert(!session.allowsBridge(generation, original, true, 10));
    assert(session.sourceIdentity() == "tablet-two");
    session.close();
    assert(!session.active() && session.url().isEmpty());
    assert(!session.allowsBridge(replacement, original, true, 10));
    assert(session.open(original, Surface::Tablet, " ") == 0);
    assert(session.open(QUrl("https://user:secret@example.com/"), Surface::Tablet, "tablet") == 0);

    generation = session.open(original, Surface::Tablet, "tablet");
    assert(session.allowsScriptURL(QUrl("qrc:/scripts/system/page.js"), "qrc:/scripts"));
    assert(!session.allowsScriptURL(QUrl("qrc:/scripts/system/page.js"), "qrc:/"));
    assert(!session.allowsScriptURL(QUrl("qrc:/scripts-other/page.js"), "qrc:/scripts"));
    assert(!session.allowsScriptURL(QUrl("qrc:/scripts/../private/page.js"), "qrc:/scripts"));
    assert(!session.allowsScriptURL(QUrl("qrc:/scripts/%2e%2e/private/page.js"), "qrc:/scripts"));
    assert(!session.allowsScriptURL(QUrl("qrc:/scripts\\private/page.js"), "qrc:/scripts"));

    generation = session.open(QUrl("qrc:/html/app.html?version=1"), Surface::Tablet, "bundled-app", "qrc:/html");
    assert(generation != 0);
    assert(session.allowsBridge(generation, QUrl("qrc:/html/app.html?version=2#anchor"), true, 10));
    assert(!session.allowsBridge(generation, QUrl("qrc:/html/other.html"), true, 10));
    assert(session.allowsNavigation(generation, QUrl("qrc:/html/other.html"), true, "GET"));
    assert(!session.allowsNavigation(generation, QUrl("qrc:/private/page.html"), true, "GET"));
    assert(session.open(QUrl("qrc:/html/app.html"), Surface::Tablet, "bundled-app") == 0);

    QTemporaryDir directory;
    assert(directory.isValid());
    QDir root(directory.path());
    assert(root.mkdir("packaged"));
    QFile allowed(root.filePath("packaged/app.html"));
    assert(allowed.open(QIODevice::WriteOnly));
    allowed.write("<p>Packaged HTML</p>");
    allowed.close();
    QFile privateFile(root.filePath("private.html"));
    assert(privateFile.open(QIODevice::WriteOnly));
    privateFile.write("private");
    privateFile.close();
    assert(QFile::link(privateFile.fileName(), root.filePath("packaged/escape.html")));
    const auto package = root.filePath("packaged");
    const auto document = QUrl::fromLocalFile(allowed.fileName());
    generation = session.open(document, Surface::Tablet, "packaged", package);
    assert(generation != 0);
    assert(session.allowsBridge(generation, document, true, 10));
    assert(session.allowsScriptURL(document, package));
    assert(!session.allowsScriptURL(QUrl::fromLocalFile(privateFile.fileName()), package));
    assert(!session.allowsScriptURL(QUrl::fromLocalFile(root.filePath("packaged/escape.html")), package));
    assert(!session.allowsScriptURL(document, "/"));
    assert(!session.allowsScriptURL(document, ""));
    assert(session.open(QUrl::fromLocalFile(privateFile.fileName()), Surface::Tablet, "packaged", package) == 0);
    std::cout << "PASS actual EmbeddedWebSession: navigation, isolated bridge, lifecycle, packaged grants\n";
}
