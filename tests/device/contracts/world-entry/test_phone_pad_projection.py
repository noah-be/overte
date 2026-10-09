"""Exercise actual radial clipping, including the Pixel near-vertical regression."""
from pathlib import Path
import os
import resource
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class PhonePadProjection(unittest.TestCase):
    def test_actual_clipping_and_original_negative_control(self):
        name = "libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.cpp"
        current = (ROOT / name).read_text()
        original = Path(__file__).with_name("phone-pad-projection-original.inc").read_text()
        with tempfile.TemporaryDirectory(prefix="overte-pad-projection-") as tmp:
            for source, succeeds in ((current, True), (original, False)):
                body = source.split("glm::vec2 TouchscreenVirtualPadDevice::clippedPointInCircle(", 1)[1].split("\nvoid TouchscreenVirtualPadDevice::processInputDeviceForMove", 1)[0]
                code = r'''#include <glm/glm.hpp>
#include <cmath>
#include <cassert>
#include <algorithm>
using glm::vec2;
float clip(float n, float lo, float hi) { return std::clamp(n, lo, hi); }
struct TouchscreenVirtualPadDevice { static vec2 clippedPointInCircle(float,vec2,vec2); };
''' + "glm::vec2 TouchscreenVirtualPadDevice::clippedPointInCircle(" + body + r'''
int main() {
 const vec2 center(253.04f, 827.0f); const float radius=121.3f;
 for (float dx : {-177.f,-1.f,-.1f,-.04f,-.001f,0.f,.001f,.04f,.1f,1.f,177.f}) {
  for (float dy : {-177.f,-1.f,0.f,1.f,177.f}) {
   const vec2 delta(dx,dy), point=center+delta;
   const vec2 clipped=TouchscreenVirtualPadDevice::clippedPointInCircle(radius,center,point);
   assert(std::isfinite(clipped.x) && std::isfinite(clipped.y));
   const float length=glm::length(point-center);
   const vec2 expected=length<=radius ? point : center+(point-center)*(radius/length);
   assert(glm::length(clipped-expected)<.01f);
   assert(glm::length(clipped-center)<=radius+.01f);
  }
 }
 const vec2 zero=TouchscreenVirtualPadDevice::clippedPointInCircle(radius,center,center);
 assert(zero==center);
}
'''
                cpp=Path(tmp)/"test.cpp"; exe=Path(tmp)/"test";cpp.write_text(code)
                includes = (["-I", os.environ["OVERTE_TEST_GLM_INCLUDE"]]
                            if os.environ.get("OVERTE_TEST_GLM_INCLUDE") else [])
                compilation = subprocess.run(["c++","-std=c++17",*includes,str(cpp),"-o",str(exe)],capture_output=True,timeout=30)
                self.assertEqual(compilation.returncode, 0, compilation.stderr.decode())
                result=subprocess.run([str(exe)],capture_output=True,timeout=5)
                if succeeds: self.assertEqual(result.returncode,0,result.stderr)
                else: self.assertNotEqual(result.returncode,0,"Original unstable projection unexpectedly passed")

if __name__ == "__main__": unittest.main()
