"""Actual request history: sender concurrency, reply order and clock/reset behavior."""
from pathlib import Path
import shlex,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[4]
fixture=r'''
#include "libraries/networking/src/DomainListRequestHistory.h"
#include <cassert>
#include <thread>
#include <vector>
#include <set>
int main(){
 DomainListRequestHistory h;
 const auto a=h.issued(10000),b=h.issued(10000),c=h.issued(9000);
 assert(a!=b&&b!=c&&a!=c);
 quint64 wall=0;assert(h.accept(c,&wall)&&wall==9000);assert(!h.accept(a)&&!h.accept(b));
 assert(h.accept(c)); // sibling packet-list segment
 h.clear();assert(!h.accept(c));const auto d=h.issued(9000);assert(d!=c&&h.accept(d));
 std::vector<quint64> tokens(64);std::vector<std::thread> senders;
 for(int i=0;i<8;++i)senders.emplace_back([&,i]{for(int j=0;j<8;++j)tokens[i*8+j]=h.issued(9000);});
 for(auto& thread:senders)thread.join();
 assert(std::set<quint64>(tokens.begin(),tokens.end()).size()==64);
 const auto newest=*std::max_element(tokens.begin(),tokens.end());assert(h.accept(newest));
 for(auto token:tokens)if(token!=newest)assert(!h.accept(token));
 for(int i=0;i<10000;++i)h.issued(8000);
 assert(!h.accept(newest));const auto fresh=h.issued(7000);assert(h.accept(fresh,&wall)&&wall==7000);
}
'''
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
with tempfile.TemporaryDirectory(prefix='overte-domain-history-') as directory:
 p=Path(directory);(p/'test.cpp').write_text(fixture)
 subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I'+str(ROOT),str(p/'test.cpp'),'-o',str(p/'test'),*flags],check=True,timeout=30)
 subprocess.run([str(p/'test')],check=True,timeout=5)
print('PASS: clock rollback, duplicate ticks, concurrent senders, reset, stale replies, bounded retention and fresh recovery')
