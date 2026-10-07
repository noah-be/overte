// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QTimer>
#include <QLibraryInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <cstdio>
namespace QtWebEngine { void initialize(); }
int main(int argc,char** argv){
 QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
 QtWebEngine::initialize();
 QGuiApplication app(argc,argv);
 if(argc!=5)return 2;
 const QString package=QDir::cleanPath(QString::fromLocal8Bit(argv[4]));
 if(QDir::cleanPath(QLibraryInfo::location(QLibraryInfo::DataPath))!=package||QDir::cleanPath(QLibraryInfo::location(QLibraryInfo::TranslationsPath))!=package+"/translations"||QDir::cleanPath(QLibraryInfo::location(QLibraryInfo::LibraryExecutablesPath))!=package+"/libexec"){std::puts("{\"completed\":false,\"failureCategory\":\"reviewed-qt-library-path-refused\"}");return 6;}
 QQmlApplicationEngine engine;engine.addImportPath(QString::fromLocal8Bit(argv[1]));
 engine.rootContext()->setContextProperty("fixtureURL",QUrl::fromLocalFile(QString::fromLocal8Bit(argv[3])));
 engine.rootContext()->setContextProperty("fixtureStorage",qEnvironmentVariable("XDG_DATA_HOME")+"/authored-editor");
 engine.load(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));
 if(engine.rootObjects().size()!=1)return 3;
 auto* window=qobject_cast<QQuickWindow*>(engine.rootObjects().first());if(!window)return 4;
 window->requestActivate();
 QTimer poll;
 QObject::connect(&poll,&QTimer::timeout,&app,[&]{
  if(!window->property("completed").toBool())return;
  auto document=QJsonDocument::fromJson(window->property("evidence").toString().toUtf8());
  auto cases=document.object().value("cases").toArray();
  QJsonArray safe;
  for(const auto value:cases){auto entry=value.toObject();QJsonObject row{{"kind",entry.value("kind")},{"passed",entry.value("passed").toBool()},{"stage",entry.value("stage")},{"errorCategory",entry.value("errorCategory")},{"targetChecks",entry.value("targetChecks")},{"domRefusal",entry.value("domRefusal")},{"nativeCommitObserved",entry.value("nativeCommitObserved").toBool()},{"nativeCommitAccepted",entry.value("nativeCommitAccepted").toBool()},{"nativeGuardStage",entry.value("nativeGuardStage")},{"nativeGuardReason",entry.value("nativeGuardReason")}};
   for(const auto* key:{"beforeLength","beforeSelectionLength","afterLength","afterSelectionLength"})row.insert(key,entry.value(key).toInt(-1));
   safe.append(row);
  }
  QJsonObject report{{"qtLibraryPathsMatched",true},{"completed",true},{"passed",window->property("passed").toBool()},{"cases",safe}};
  std::puts(QJsonDocument(report).toJson(QJsonDocument::Compact).constData());
  app.exit(window->property("passed").toBool()?0:1);
 });poll.start(20);
 QTimer::singleShot(60000,&app,[&]{std::puts("{\"completed\":false,\"failureCategory\":\"owned-editor-deadline\"}");app.exit(5);});
 return app.exec();
}
