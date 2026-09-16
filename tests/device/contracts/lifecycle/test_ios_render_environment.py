"""Production render-mode getter: cache launch environment, retain JSON reload."""
from pathlib import Path
import os,shlex,subprocess,tempfile
from test_login_dialog_domain_receiver import block
ROOT=Path(__file__).resolve().parents[4]
baseline=os.environ.get('OVERTE_RENDER_ENV_BASELINE')
source=subprocess.check_output(['git','show',baseline+':libraries/shared/src/shared/IOSRuntimeLogging.h'],cwd=ROOT,text=True) if baseline else (ROOT/'libraries/shared/src/shared/IOSRuntimeLogging.h').read_text()
method=block(source,'inline QByteArray iosRuntimeRenderDiagnosticMode()')
fixture=r'''
#include <QByteArray>
#include <QJsonObject>
#include <QString>
#include <atomic>
#include <thread>
#include <vector>
#include <cassert>
std::atomic<int> reads{0};QByteArray launch;QJsonObject config;
QByteArray readLaunch(const char*){++reads;return launch;}
QJsonObject iosRuntimeDiagnosticConfig(){return config;}
#define qgetenv readLaunch
/* METHOD */
int main(int argc,char**argv){
 const bool overridden=argc>1;launch=overridden?" FULL-SCISSOR ":"";
 assert(iosRuntimeRenderDiagnosticMode()==(overridden?"full-scissor":""));
 config.insert("renderDiagnosticMode"," DEPTH-OFF ");
 assert(iosRuntimeRenderDiagnosticMode()==(overridden?"full-scissor":"depth-off"));
 std::vector<std::thread> threads;for(int i=0;i<8;++i)threads.emplace_back([&]{for(int n=0;n<1000;++n)assert(iosRuntimeRenderDiagnosticMode()==(overridden?"full-scissor":"depth-off"));});
 for(auto& t:threads)t.join();
 config.insert("renderDiagnosticMode","off");assert(iosRuntimeRenderDiagnosticMode()==(overridden?"full-scissor":"off"));
 assert(reads==1);
}
'''
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
with tempfile.TemporaryDirectory(prefix='overte-render-env-') as directory:
 p=Path(directory);(p/'test.cpp').write_text(fixture.replace('/* METHOD */',method))
 subprocess.run(['c++','-std=c++17','-fPIC','-pthread',str(p/'test.cpp'),'-o',str(p/'test'),*flags],check=True,timeout=30)
 for args in ([],['override']):
  result=subprocess.run([str(p/'test'),*args],capture_output=True,text=True,timeout=5)
  if baseline:assert result.returncode!=0 and 'reads==1' in result.stderr,result.stderr
  else:assert result.returncode==0,result.stderr
print('EXPECTED BASELINE FAILURE: repeated environment lock in draw path' if baseline else 'PASS: one launch read, concurrent draw callers, environment precedence and live JSON changes')
