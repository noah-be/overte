#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""CPU control-flow contracts for the exact whole-password candidate method; no Qt/Blink claim."""
from pathlib import Path
import subprocess,tempfile,unittest
HERE=Path(__file__).resolve().parent

def section(source,start,end):
    first=source.index(start);return source[first:source.index(end,first)]

STUBS=r'''
#include <string>
#include <vector>
#include <functional>
#include <cstdlib>
using uint=unsigned;using ushort=unsigned short;
#define Q_INVOKABLE
#define QStringLiteral(x) QString(x)
struct QChar { ushort code;ushort unicode() const{return code;}
static bool isHighSurrogate(ushort x){return x>=0xd800&&x<=0xdbff;}
static bool isLowSurrogate(ushort x){return x>=0xdc00&&x<=0xdfff;}
static uint surrogateToUcs4(ushort h,ushort l){return 0x10000+((h-0xd800)<<10)+(l-0xdc00);}};
struct QString { std::u16string data;
QString()=default;QString(const char* s){while(*s)data.push_back(*s++);}QString(std::u16string s):data(s){}
bool isEmpty()const{return data.empty();}int size()const{return (int)data.size();}
QChar at(int i)const{return{(ushort)data.at(i)};}};
struct QObject { bool alive=true;virtual ~QObject()=default;};
struct QQuickWindow:QObject{};struct QQuickItem:QObject { QQuickWindow* ownWindow=nullptr;QQuickWindow* window(){return ownWindow;} };
template<class T> struct QPointer {T* p;QPointer(T* t):p(t){}operator T*()const{return p&&p->alive?p:nullptr;}explicit operator bool()const{return p&&p->alive;}T* operator->()const{return p;} };
template<class T> T qobject_cast(QObject* p){return dynamic_cast<T>(p);}
namespace Qt {enum{ImHints=1,ImhHiddenText=2,NoModifier=0};}
namespace QEvent {enum{KeyPress=1,KeyRelease=2};}
struct Value {bool valid=true;int hints=Qt::ImhHiddenText;bool isValid(){return valid;}int toInt(){return hints;}};
struct Event {bool accepted=true;virtual ~Event()=default;bool isAccepted(){return accepted;}};
struct QInputMethodQueryEvent:Event {Value v;explicit QInputMethodQueryEvent(int){}Value value(int){return v;}};
struct QInputMethodEvent:Event {QString commit;void setCommitString(const QString& s){commit=s;}};
struct QKeyEvent:Event {int type,key;QString text;QKeyEvent(int t,int k,int m,const QString& s,bool repeat,int count):type(t),key(k),text(s){if(m||repeat||count!=1)std::abort();}};
struct QCoreApplication {static std::function<bool(QObject*,Event*)> dispatch;static bool sendEvent(QObject* p,Event* e){return dispatch(p,e);}};
std::function<bool(QObject*,Event*)> QCoreApplication::dispatch;
struct NativeInput:QObject {QString _webCommitStage,_webCommitGuard;QQuickItem* owner=nullptr;bool current=true;int checks=0;
QQuickItem* ownerItem(){return owner;}bool refuseWebGuard(const char* s){_webCommitGuard=QString(s);return false;}
bool webPasswordTargetCurrent(QQuickItem* item,QQuickItem* root,QQuickItem* o,QQuickWindow* w){++checks;return current&&item&&root&&o&&w&&item->alive&&root->alive&&o->alive&&w->alive;}
'''
TAIL=r'''
};
void require(bool b){if(!b)std::exit(86);}
int main(){
for(auto text:{std::u16string(u"A"),std::u16string(u"é"),std::u16string(u"Aé👋Z"),std::u16string(65536,u'a'),std::u16string(32768,u'é')}) {
for(int failure=0;failure<10;++failure){
NativeInput n;QQuickItem item,root,owner;QQuickWindow window;owner.ownWindow=&window;n.owner=&owner;
int queries=0,keys=0,commits=0;QString delivered;
QCoreApplication::dispatch=[&](QObject*,Event* event){
if(auto* q=dynamic_cast<QInputMethodQueryEvent*>(event)){++queries;if(failure==1)q->v.valid=false;if(failure==2)q->v.hints=0;if(failure==3)n.current=false;if(failure==4)n.alive=false;return true;}
if(auto* e=dynamic_cast<QInputMethodEvent*>(event)){++commits;delivered=e->commit;}
if(dynamic_cast<QKeyEvent*>(event))++keys;
if(failure==5)return false;if(failure==6)event->accepted=false;
if(failure==7)n.current=false;if(failure==8)n.alive=false;if(failure==9)item.alive=false;return true;};
bool ok=n.commitWebPasswordText(&item,&root,QString(text));
require(queries==1);require(ok==(failure==0));require(keys==0);
if(failure>=1&&failure<=4){require(commits==0);continue;}
require(commits==1&&delivered.data==text);
}}
// Original limits and paired scalar admission are repeated in the actual C++ validator.
for(auto text:{std::u16string(),std::u16string(1,0),std::u16string(u"a\nb"),std::u16string(u"a\tb"),std::u16string(1,127),std::u16string(1,0xd800),std::u16string(1,0xdc00),std::u16string({0xd800,u'A'}),std::u16string({u'A',0xdc00}),std::u16string(65537,u'a'),std::u16string(32769,u'é'),std::u16string(21846,u'世')}){
NativeInput n;int calls=0;QCoreApplication::dispatch=[&](QObject*,Event*){++calls;return true;};require(!n.commitWebPasswordText(nullptr,nullptr,QString(text)));require(calls==0);}
NativeInput n;QQuickItem i,r,o;QQuickWindow w;o.ownWindow=&w;n.owner=&o;n.current=false;int calls=0;QCoreApplication::dispatch=[&](QObject*,Event*){++calls;return true;};require(!n.commitWebPasswordText(&i,&r,QString(u"Aé👋Z")));require(calls==0);
require(NativeInput::passwordTextValid(QString(std::u16string(16384,0xd83d)+std::u16string(16384,0xdc4b)))==false);
std::u16string pairs;for(int j=0;j<16384;++j)pairs+=u"👋";require(NativeInput::passwordTextValid(QString(pairs)));pairs+=u"a";require(!NativeInput::passwordTextValid(QString(pairs)));
}
'''
class NativeRoute(unittest.TestCase):
    def test_actual_method_fulltext_routes_and_bounds(self):
        candidate=(HERE/'native-input.cpp').read_text()
        def source(cpp):
            return STUBS+section(cpp,'    Q_INVOKABLE bool commitWebPasswordText(','    // The offscreen')+section(cpp,'    static bool passwordTextValid(','    bool deliver(')+TAIL
        with tempfile.TemporaryDirectory(prefix='scalar-cpu-') as tmp:
            path=Path(tmp)/'candidate';path.with_suffix('.cpp').write_text(source(candidate))
            subprocess.run(['g++','-std=c++17','-O0',str(path.with_suffix('.cpp')),'-o',str(path)],check=True,capture_output=True,timeout=15)
            result=subprocess.run([str(path)],capture_output=True,timeout=2)
            self.assertEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
