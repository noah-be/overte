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
#include "libraries/networking/src/DataServerAccountInfo.h"
Q_DECLARE_METATYPE(DataServerAccountInfo)
#include "account-types.inc"
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
 OAuthAccessToken token;token.token="token-fixture";token.refreshToken="refresh-fixture";token.expiryTimestamp=123456789;token.tokenType="Bearer";
 QByteArray fields;QDataStream fieldWriter(&fields,QIODevice::WriteOnly);
 fieldWriter<<token<<QString("username-fixture")<<QString("xmpp-fixture")<<QString("discourse-fixture")
  <<QUuid()<<QByteArray("private-key-fixture")<<QUuid("{11111111-1111-1111-1111-111111111111}")
  <<QUuid("{22222222-2222-2222-2222-222222222222}")<<QString("temporary-key-fixture");
 DataServerAccountInfo account;QDataStream fieldReader(fields);fieldReader>>account;assert(fieldReader.status()==QDataStream::Ok&&fieldReader.atEnd());
 QByteArray roundtrip;QDataStream fieldRoundtrip(&roundtrip,QIODevice::WriteOnly);fieldRoundtrip<<account;assert(fields==roundtrip);
 QVariantMap expected{{"https://fixture.invalid",QVariant::fromValue(account)}};auto encoded=encode(expected);
 bool ok=false;
 legacy(encoded);auto map=accountMapFromFile(ok);assert(ok&&encode(map)==encoded&&!QFileInfo::exists(location)&&store->writes==1);
 assert(writeAccountMapToFile(expected));map=accountMapFromFile(ok);assert(ok&&encode(map)==encoded);
 assert(protectedAccountCoordinator().erase(legacyAccountInput())==StoreResult::Ok);
 // Native read succeeds but protected serialization is truncated or has trailing junk.
 QList<QByteArray> invalidRecords{encoded+QByteArray("junk"),encode({{"https://fixture.invalid",42}})};
 for(int length=0;length<encoded.size();++length) invalidRecords.append(encoded.left(length));
 for(const auto& broken:invalidRecords){
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
