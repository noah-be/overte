// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Qt JS executes real fixture bytes; Overte's URL resolver is extracted unchanged.
// V8/session consent remains an explicit product boundary, never a claimed host PASS.
#pragma once
#include <QJSEngine>
#include <QQmlEngine>
#include <QUrl>
#include <QFile>
#include <memory>
struct BundleContextInfo { QString name; QString fileName() { return name; } };
struct BundleContext {
    QString name;
    std::shared_ptr<BundleContextInfo> functionContext() { return std::make_shared<BundleContextInfo>(BundleContextInfo{name}); }
    std::shared_ptr<BundleContext> parentContext() { return {}; }
};
using ScriptContextPointer = std::shared_ptr<BundleContext>;
struct BundleEngine { BundleContext context; BundleContext* currentContext(){ return &context; } };
class ScriptManager : public QObject {
    Q_OBJECT
public:
    QJSEngine js;
    BundleEngine state;
    BundleEngine* _engine { &state };
    QString _parentURL, _fileNameString;
    QUrl resolvePath(const QString& include) const;
    QUrl expandScriptUrl(const QUrl& url) const { return url; } // file URLs do not need packaged alias expansion.
    Q_INVOKABLE void include(const QString& path) {
        const auto url=resolvePath(path);
        QFile file(url.toLocalFile());
        if(!file.open(QFile::ReadOnly)){js.throwError("Missing companion: "+path);return;}
        auto parent=state.context.name;state.context.name=url.toString();
        auto result=js.evaluate(QString::fromUtf8(file.readAll()),url.toString());
        state.context.name=parent;
        if(result.isError())js.throwError(result.toString());
    }
    QJSValue run(const QUrl& url) {
        state.context.name=_fileNameString=url.toString();
        QQmlEngine::setObjectOwnership(this,QQmlEngine::CppOwnership);
        js.globalObject().setProperty("Script",js.newQObject(this));
        QFile file(url.toLocalFile());
        if(!file.open(QFile::ReadOnly))return js.evaluate("throw new Error('missing main file')");
        return js.evaluate(QString::fromUtf8(file.readAll()),url.toString());
    }
};
#include "script-resolver-body.inc"
