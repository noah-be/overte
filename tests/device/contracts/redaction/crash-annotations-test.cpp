#include "CrashHandler.h"
#include "CrashHandlerBackend.h"
#include <cassert>
#include <map>
#include <vector>
Q_LOGGING_CATEGORY(crash_handler,"crash-annotation-test")
static std::map<std::string,std::string> forwarded;
static QString diagnostics;
static std::string transportToken,transportUrl;
bool startCrashHandler(std::string,std::string url,std::string token){transportUrl=url;transportToken=token;return true;}
void setCrashAnnotation(std::string key,std::string value){forwarded[key]=value;}
void startCrashHookMonitor(QCoreApplication*){}
void setCrashReportingEnabled(bool){}
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);
 qInstallMessageHandler([](QtMsgType,const QMessageLogContext&,const QString& text){diagnostics+=text;});
 auto& handler=CrashHandler::getInstance();
 const std::vector<std::string> privateKeys={"sentry[user][username]","metaverse_session_id","domain","avatar","address","machine_fingerprint","private-key-canary","display_plugin","sentry[contexts][gpu][name]"};
 const QString secret="https://private-target-canary.invalid/?token=credential-canary";
 handler.setUrl(secret);handler.setToken("transport-token-canary");
 for(const auto& key:privateKeys){handler.setAnnotation(key,secret);}
 handler.setAnnotation("program","interface");handler.setAnnotation("shutdown","1");
 handler.setAnnotation("main_thread_id","123");
 assert(forwarded.empty());assert(handler.start());
 assert(forwarded.size()==3 && forwarded["program"]=="interface" && forwarded["main_thread_id"]=="123");
 assert(transportUrl==secret.toStdString() && transportToken=="transport-token-canary");
 for(const auto& key:privateKeys){handler.setAnnotation(key,secret.toStdString());}
 handler.setAnnotation("program",secret);handler.setAnnotation("shutdown","credential-canary");
 handler.setAnnotation("main_thread_id","123-user-canary");handler.setAnnotation("gpu_memory",static_cast<const char*>(nullptr));
 assert(forwarded.size()==3 && forwarded["program"]=="interface" && forwarded["shutdown"]=="1" && forwarded["main_thread_id"]=="123");
 handler.setAnnotation("gpu_memory","18446744073709551615");
 for(const char* invalid:{"18446744073709551616","999999999999999999999","-1","1.0","123-secret"}){
  handler.setAnnotation("gpu_memory",invalid);assert(forwarded["gpu_memory"]=="18446744073709551615");
 }
 handler.setAnnotation("type","7");handler.setAnnotation("type","8");assert(forwarded["type"]=="7");
 handler.setUrl("https://later-target-canary.invalid");handler.setToken("later-token-canary");
 assert(!diagnostics.contains("canary"));
}
