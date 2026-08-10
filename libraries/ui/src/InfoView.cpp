//
//
//  InfoView.h
//
//  Created by Bradley Austin Davis 2015/04/25
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "InfoView.h"

#include <SettingHandle.h>
#include <PathUtils.h>
#include <QDir>
#include <QFile>
#include <QXmlStreamReader>
const QUrl InfoView::QML{ "InfoView.qml" };
const QString InfoView::NAME{ "InfoView" };

Setting::Handle<QString> infoVersion("info-version", QString());

static bool registered{ false };

InfoView::InfoView(QQuickItem* parent) : QQuickItem(parent) {
    registerType();
}

void InfoView::registerType() {
    if (!registered) {
        qmlRegisterType<InfoView>("Hifi", 1, 0, NAME.toLocal8Bit().constData());
        registered = true;
    }
}

QString fetchVersion(const QUrl& url) {
    QString fileName;
    if (url.isLocalFile()) {
        fileName = url.toLocalFile();
    } else if (url.scheme() == QStringLiteral("qrc")) {
        fileName = QStringLiteral(":") + url.path();
    } else {
        return {};
    }

    QFile file(fileName);
    if (!file.open(QIODevice::ReadOnly)) {
        return {};
    }

    QXmlStreamReader reader(&file);
    while (!reader.atEnd()) {
        reader.readNext();
        if (!reader.isStartElement() || reader.name() != QStringLiteral("input")) {
            continue;
        }
        const auto attributes = reader.attributes();
        if (attributes.value(QStringLiteral("id")) == QStringLiteral("version")) {
            return attributes.value(QStringLiteral("value")).toString().trimmed();
        }
    }
    return {};
}

void InfoView::show(const QString& path, bool firstOrChangedOnly, QString urlQuery) {
    registerType();
    QUrl url;
    if (QDir(path).isRelative()) {
        url = PathUtils::resourcesUrl(path);
    } else {
        url = QUrl::fromLocalFile(path);
    }
    url.setQuery(urlQuery);

    if (firstOrChangedOnly) {
        const QString lastVersion = infoVersion.get();
        const QString version = fetchVersion(url);
        // If we have version information stored
        if (!lastVersion.isNull()) {
            // Check to see the document version.  If it's valid and matches
            // the stored version, we're done, so exit
            if (version.isNull() || version == lastVersion) {
                return;
            }
        }
        infoVersion.set(version);
    }
    if (auto offscreenUI = DependencyManager::get<OffscreenUi>()) {
        QString infoViewName(NAME + "_" + path);
        offscreenUI->show(QML, NAME + "_" + path, [=] (QQmlContext* context, QObject* newObject) {
            QQuickItem* item = dynamic_cast<QQuickItem*>(newObject);
            item->setWidth(1024);
            item->setHeight(720);
            InfoView* newInfoView = newObject->findChild<InfoView*>();
            Q_ASSERT(newInfoView);
            newInfoView->parent()->setObjectName(infoViewName);
            newInfoView->setUrl(url);
        });
    }
}

QUrl InfoView::url() {
    return _url;
}

void InfoView::setUrl(const QUrl& url) {
    if (url != _url) {
        _url = url;
        emit urlChanged();
    }
}
