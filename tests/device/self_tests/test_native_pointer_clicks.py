"""Compile and execute the production native entity click forwarding callbacks."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[3]

class NativePointerClickTests(unittest.TestCase):
    def test_primary_click_lifecycle_and_non_primary_isolation(self):
        if not shutil.which("c++"):self.skipTest("C++ compiler unavailable")
        code=(SOURCE/"libraries/entities-renderer/src/EntityTreeRenderer.cpp").read_text()
        start=code.index("    // Begin native pointer click lifecycle.")
        end=code.index("    // End native pointer click lifecycle.",start)
        callbacks=code[start:end]
        driver=r"""
#include <cassert>
#include <functional>
#include <memory>
#include <vector>
#define emit
using QUuid=int;
struct PointerEvent {
 enum Button {NoButtons=0,PrimaryButton=1,SecondaryButton=2};
 Button button; Button getButton() const {return button;}
};
struct PointerManager {
 using Callback=std::function<void(const QUuid&,const PointerEvent&)>;
 Callback begin,hold,end;
 void triggerBeginEntity(const QUuid&,const PointerEvent&) {}
 void triggerContinueEntity(const QUuid&,const PointerEvent&) {}
 void triggerEndEntity(const QUuid&,const PointerEvent&) {}
};
struct EntitySignals {
 std::vector<int> downs,holds,ups;
 void clickDownOnEntity(int id,const PointerEvent&){downs.push_back(id);}
 void holdingClickOnEntity(int id,const PointerEvent&){holds.push_back(id);}
 void clickReleaseOnEntity(int id,const PointerEvent&){ups.push_back(id);}
};
template<class F> void connect(PointerManager* p,
 void(PointerManager::*signal)(const QUuid&,const PointerEvent&),EntitySignals*,F callback) {
 if(signal==&PointerManager::triggerBeginEntity)p->begin=callback;
 if(signal==&PointerManager::triggerContinueEntity)p->hold=callback;
 if(signal==&PointerManager::triggerEndEntity)p->end=callback;
}
int main(){
 struct Owner {PointerManager value;PointerManager* data(){return &value;}} pointerManager;
 EntitySignals events;auto entityScriptingInterface=&events;
 // PRODUCTION_CALLBACKS
 for(auto button:{PointerEvent::SecondaryButton,PointerEvent::NoButtons}) {
  pointerManager.value.begin(9,{button});pointerManager.value.hold(9,{button});pointerManager.value.end(9,{button});
 }
 assert(events.downs.empty()&&events.holds.empty()&&events.ups.empty());
 pointerManager.value.begin(42,{PointerEvent::PrimaryButton});
 for(int i=0;i<5;++i)pointerManager.value.hold(42,{PointerEvent::PrimaryButton});
 pointerManager.value.end(42,{PointerEvent::PrimaryButton});
 assert(events.downs==std::vector<int>{42});assert(events.holds==std::vector<int>(5,42));
 assert(events.ups==std::vector<int>{42});
}
""".replace("// PRODUCTION_CALLBACKS",callbacks)
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch);(root/"test.cpp").write_text(driver)
            subprocess.run(["c++","-std=c++17","-Wall","-Wextra","-Werror",str(root/"test.cpp"),
                "-o",str(root/"test")],check=True,capture_output=True,timeout=30)
            subprocess.run([str(root/"test")],check=True,capture_output=True,timeout=5)

if __name__=="__main__":unittest.main()
