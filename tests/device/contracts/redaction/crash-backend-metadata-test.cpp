#include <QCoreApplication>
#include <QLoggingCategory>
#include <QFileInfo>
#include <QMap>
#include <QString>
#include <map>
#include <string>
#include <cassert>
Q_LOGGING_CATEGORY(crash_handler,"crash-backend-metadata-test")
namespace BuildInfo {const char* VERSION="1.2.3";const char* BUILD_NUMBER="4";const char* BUILD_TYPE_STRING="fixture";}
struct FingerprintUtils {static QString getMachineFingerprint(){return "device-canary";}};
static QString uuidStringWithoutCurlyBraces(QString value){return value;}
static QString diagnostics;
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);
 qInstallMessageHandler([](QtMsgType,const QMessageLogContext&,const QString& text){diagnostics+=text;});
 const std::string crashToken="token-canary";
 {
  std::map<std::string,std::string> annotations;
  // CRASHPAD_METADATA
  assert(annotations.size()==4 && annotations.at("sentry[release]")=="1.2.3");
  for(const auto& entry:annotations){assert(entry.first.find("canary")==std::string::npos && entry.second.find("canary")==std::string::npos);}
 }
 {
  QMap<QString,QString> annotations;
  // BREAKPAD_METADATA
  assert(annotations.size()==3 && annotations["version"]=="1.2.3");
  for(auto it=annotations.begin();it!=annotations.end();++it){assert(!it.key().contains("canary")&&!it.value().contains("canary"));}
 }
 const QString exeLink="/private/path-canary",interfaceDir="/private/user-canary";
 const QFileInfo exeInfo("/private/executable-canary");
 const char* CRASHPAD_HANDLER_NAME="handler";
 const std::string CRASHPAD_HANDLER_PATH="/private/handler-canary",crashpadDbPath="/private/database-canary";
 struct Uuid{std::string ToString()const{return "report-canary";}};
 struct Report{Uuid uuid;} report;
 const bool enabled=true;
 // BACKEND_LOGS
 assert(!diagnostics.contains("canary"));
}
