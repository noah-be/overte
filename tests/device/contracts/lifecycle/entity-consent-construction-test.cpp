#include <QString>
#include <QUrl>
#include <memory>
#include <functional>
#include <cassert>
struct ScriptValue {
    bool function{false}, object{false}, error{false};
    std::function<ScriptValue()> constructor;
    bool isFunction()const{return function;}
    bool isObject()const{return object;}
    bool isError()const{return error;}
    ScriptValue construct()const{return constructor();}
};
struct ScriptSyntaxCheckResult {
    enum State {Valid, Invalid}; State value{Valid};
    State state()const{return value;} QString errorMessage()const{return "invalid";}
};
struct Program {std::shared_ptr<ScriptSyntaxCheckResult> result; auto checkSyntax(){return result;}};
struct Engine {
    std::function<ScriptValue()> evaluateCallback;
    std::shared_ptr<Program> program;
    auto newProgram(const QString&,const QString&){return program;}
    ScriptValue evaluate(const QString&,const QString&){return evaluateCallback();}
    bool hasUncaughtException()const{return false;}
    ScriptValue nullValue()const{return {};}
    void clearExceptions(){}
};
struct ScriptException{virtual ~ScriptException()=default;};
struct ScriptEngineException:ScriptException{ScriptEngineException(const char*,const char*){}};
struct EntityScriptStatus{enum Status{RUNNING,ERROR_RUNNING_SCRIPT};};
struct Details{int status{};ScriptValue scriptObject;std::shared_ptr<int> consentRequest;int64_t lastModified{};QUrl definingSandboxURL;};
struct Fixture {
    Engine engine;Engine* _engine{&engine};
    QString contents, fileName, scriptOrURL{"https://fixture.invalid/script.js"}, entityID;
    QUrl currentSandboxURL;
    std::shared_ptr<int> consent{std::make_shared<int>(1)};
    int installed{0},errors{0},syntaxPassed{0};bool active{true};Details saved;
    bool consentCurrent()const{return active;}
    void doWithEnvironment(const QString&,const QUrl&,std::function<void()> operation,const std::shared_ptr<int>&){if(active){operation();}}
    void setError(const QString&,int){++errors;}
    void unhandledException(std::shared_ptr<ScriptException>){}
    void setEntityScriptDetails(const QString&,const QString&,const Details& details){++installed;saved=details;}
    void construct(){
        Details newDetails;int64_t lastModified=0;
        // ACTUAL_CONSTRUCTION
    }
    void syntax(){
        // ACTUAL_SYNTAX
        ++syntaxPassed;
    }
};
int main(){
    for(int mode=0;mode!=6;++mode){
        Fixture f;int evaluated=0,constructed=0;
        f.engine.evaluateCallback=[&]{
            ++evaluated;if(mode==1){f.active=false;}
            ScriptValue value;value.function=mode!=3;
            value.constructor=[&]{++constructed;if(mode==2){f.active=false;}ScriptValue object;object.object=true;object.error=mode==4;return object;};
            return value;
        };
        if(mode==5){f.active=false;}
        f.construct();
        assert(evaluated==(mode==5?0:1));
        assert(constructed==((mode==1||mode==3||mode==5)?0:1));
        assert(f.installed==(mode==0?1:0));
        if(mode==0){assert(f.saved.consentRequest==f.consent && f.saved.status==EntityScriptStatus::RUNNING);}
        if(mode==3){assert(f.errors==1);}
    }
    for(int mode=0;mode!=4;++mode){
        Fixture f;
        if(mode!=0){f.engine.program=std::make_shared<Program>();}
        if(mode>1){f.engine.program->result=std::make_shared<ScriptSyntaxCheckResult>();}
        if(mode==2){f.engine.program->result->value=ScriptSyntaxCheckResult::Invalid;}
        f.syntax();assert(f.syntaxPassed==(mode==3?1:0));assert(f.errors==(mode==3?0:1));
    }
}
