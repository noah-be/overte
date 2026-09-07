// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QDataStream>
#include <QVariant>
#include <QFile>
#include <QFileInfo>
#include <QTemporaryDir>
#include <cassert>
#include <iostream>
#include "security/storage/ProtectedAccountStore.h"
using namespace overte::security;
static QString location;
QString accountFilePath(){return location;}
#include "methods.inc"
struct Store:ProtectedAccountStore {
 AccountBytes bytes;StoreResult status=StoreResult::Absent;bool mismatch=false;int writes=0;
 StoreResult read(AccountBytes& output)override{output=bytes;return status;}
 StoreResult write(const AccountBytes& input)override{++writes;bytes=input;if(mismatch)bytes.push_back(1);status=StoreResult::Ok;return status;}
 StoreResult erase()override{bytes.clear();status=StoreResult::Absent;return StoreResult::Ok;}
};
QByteArray encode(const QVariantMap& map){QByteArray data;QDataStream stream(&data,QIODevice::WriteOnly);stream<<map;assert(stream.status()==QDataStream::Ok);return data;}
void legacy(const QByteArray& bytes){QFile file(location);assert(file.open(QIODevice::WriteOnly));assert(file.write(bytes)==bytes.size());}
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);QTemporaryDir temp;assert(temp.isValid());location=temp.path()+"/AccountInfo.bin";
 auto store=std::make_shared<Store>();assert(protectedAccountCoordinator().install(store));
 QVariantMap expected{{"fixture",QString("opaque-value")}};auto encoded=encode(expected);
 bool ok=false;
 legacy(encoded);auto map=accountMapFromFile(ok);assert(ok&&map==expected&&!QFileInfo::exists(location)&&store->writes==1);
 assert(writeAccountMapToFile({{"replacement",42}}));map=accountMapFromFile(ok);assert(ok&&map.value("replacement").toInt()==42);
 assert(protectedAccountCoordinator().erase(legacyAccountInput())==StoreResult::Ok);
 // Native read succeeds but protected serialization is truncated or has trailing junk.
 for(auto broken:{QByteArray(1,'x'),encoded+QByteArray("junk")}){
  legacy(encoded);store->bytes.assign(broken.begin(),broken.end());store->status=StoreResult::Ok;
  map=accountMapFromFile(ok);assert(!ok&&map.isEmpty());
  assert(QFileInfo::exists(location)&&"invalid protected map must not delete recoverable legacy data");
  AccountBytes output;assert(protectedAccountCoordinator().read(output,legacyAccountInput())==StoreResult::ReauthRequired&&output.empty());
  assert(protectedAccountCoordinator().erase(legacyAccountInput())==StoreResult::Ok);
 }
 legacy(QByteArray(1,'x'));int writes=store->writes;map=accountMapFromFile(ok);assert(!ok&&map.isEmpty()&&QFileInfo::exists(location)&&writes==store->writes);
 assert(protectedAccountCoordinator().erase(legacyAccountInput())==StoreResult::Ok);
 legacy(encoded);store->mismatch=true;map=accountMapFromFile(ok);assert(!ok&&map.isEmpty()&&QFileInfo::exists(location));
 assert(protectedAccountCoordinator().erase(legacyAccountInput())==StoreResult::Ok);store->mismatch=false;
 map=accountMapFromFile(ok);assert(ok&&map.isEmpty());
 std::cout<<"PASS actual Qt map migration, protected corruption retention, quarantine, malformed legacy, readback and explicit erase recovery\n";
}
