// SPDX-License-Identifier: Apache-2.0
// Read only the six fixed default-avatar resources from an operator-supplied native RCC.
// Usage: audit-default-avatar <resources.rcc> <existing-private-output-directory>
#include <QCoreApplication>
#include <QResource>
#include <QFile>
#include <QCryptographicHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <cstdio>
int main(int argc,char**argv) {
 QCoreApplication app(argc,argv);
 if(argc!=3||!QResource::registerResource(QString::fromLocal8Bit(argv[1])))return 2;
 const QStringList fixed={"meshes/defaultAvatar_full.fst","meshes/mannequin/mannequin.fbx","meshes/mannequin/lambert1_Base_Color.png","meshes/mannequin/lambert1_Normal_OpenGL.png","meshes/mannequin/lambert1_Roughness.png","meshes/mannequin/Eyes.png"};
 QJsonArray result;
 for(const QString& name:fixed){ QFile source(":"+QString("/")+name);if(!source.open(QIODevice::ReadOnly)||source.size()>32*1024*1024)return 3;const QByteArray bytes=source.readAll(); const QString basename=name.section('/',-1); QFile output(QString::fromLocal8Bit(argv[2])+"/"+basename);if(!output.open(QIODevice::WriteOnly)||output.write(bytes)!=bytes.size())return 4;result.append(QJsonObject{{"packagedPath",name},{"bytes",bytes.size()},{"sha256",QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex())}}); }
 const QByteArray json=QJsonDocument(result).toJson();fwrite(json.constData(),1,json.size(),stdout);
}
