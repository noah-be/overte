// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QLoggingCategory>
#include <QCryptographicHash>
#include <QJsonObject>
#include <openssl/rsa.h>
#include <openssl/x509.h>
#include <cassert>
#include <iostream>
static bool forceSigningFailure=false;
static int checkedSign(int type,const unsigned char* message,unsigned int size,unsigned char* output,unsigned int* length,RSA* rsa){
 if(forceSigningFailure){*length=0;return 0;}
 return RSA_sign(type,message,size,output,length,rsa);
}
#define RSA_sign checkedSign
#include "actual-account.inc"
#undef RSA_sign
Q_LOGGING_CATEGORY(networking,"overte.test.account-value")
static QStringList messages;
static void capture(QtMsgType,const QMessageLogContext&,const QString& text){messages.append(text);}
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);qInstallMessageHandler(capture);
 QLoggingCategory::setFilterRules("overte.test.account-value.debug=true");
 DataServerAccountInfo account;
 const QString username="UniquePrivateUsernameCANARY";
 account.setProfileInfoFromJSON({{"data",QJsonObject{{"user",QJsonObject{{"username",username},{"xmpp_password","xmpp-fixture"},{"discourse_api_key","discourse-fixture"}}}}}});
 assert(account.getUsername()==username&&account.getXMPPPassword()=="xmpp-fixture"&&account.getDiscourseApiKey()=="discourse-fixture");
 const QUuid connection("{a8f2d013-4152-46ad-9814-47c1a1e7f093}");
 // Ephemeral host unit-test key; no product signing or release identity.
 RSA* rsa=RSA_new();BIGNUM* exponent=BN_new();assert(rsa&&exponent&&BN_set_word(exponent,RSA_F4)==1);
 assert(RSA_generate_key_ex(rsa,1024,exponent,nullptr)==1);BN_free(exponent);
 QByteArray der(i2d_RSAPrivateKey(rsa,nullptr),0);auto pointer=reinterpret_cast<unsigned char*>(der.data());assert(i2d_RSAPrivateKey(rsa,&pointer)==der.size());account.setPrivateKey(der);
 auto signature=account.getUsernameSignature(connection);assert(!signature.isEmpty());
 auto payload=username.toLower().toUtf8()+connection.toRfc4122();auto hash=QCryptographicHash::hash(payload,QCryptographicHash::Sha256);
 assert(RSA_verify(NID_sha256,reinterpret_cast<const unsigned char*>(hash.constData()),hash.size(),reinterpret_cast<const unsigned char*>(signature.constData()),signature.size(),rsa)==1);
 forceSigningFailure=true;assert(account.getUsernameSignature(connection).isEmpty());forceSigningFailure=false;
 account.setPrivateKey("invalid-key-fixture");assert(account.getUsernameSignature(connection).isEmpty());
 account.setPrivateKey({});assert(account.getUsernameSignature(connection).isEmpty());
 RSA_free(rsa);der.fill('\0');
 assert(!messages.empty());
 for(const auto& text:messages){assert(!text.contains(username,Qt::CaseInsensitive));assert(!text.contains(connection.toString(QUuid::WithoutBraces)));assert(!text.contains("xmpp-fixture")&&!text.contains("discourse-fixture")&&!text.contains("invalid-key-fixture"));}
 qInstallMessageHandler(nullptr);std::cout<<"PASS actual account profile/signature behavior, forced RSA failure and direct diagnostic canaries\n";
}
