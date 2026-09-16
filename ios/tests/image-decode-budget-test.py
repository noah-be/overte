#!/usr/bin/env python3
"""Execute the production pre-decode boundary; no Qt/native acceptance claim."""
from pathlib import Path
import subprocess
import resource
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
import tempfile
ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "libraries/image/src/image/TextureProcessing.cpp").read_text()
start = source.index("Image readBoundedImage(")
end = source.index("\nImage processRawImageData", start)
function = source[start:end]
code = r'''#include <cassert>
#include <cstdint>
#include "DecodeLimits.h"
struct Size { int w,h; int width()const{return w;} int height()const{return h;} };
struct Image { bool valid=false; Image()=default; Image(int):valid(true){} };
struct QImageReader { Size dimensions; unsigned calls=0; Size size(){return dimensions;} int read(){++calls;return 1;} };
struct Logger { template<class T> Logger& operator<<(T){return *this;} };
#define qCWarning(x) Logger()
using image::decodedImageFits;
FUNCTION
int main() {
    constexpr uint64_t budget=4096ULL*4096ULL;
    for (Size dimensions : {Size{4096,4096}, Size{1,1}, Size{8192,2048}}) {
        QImageReader reader{dimensions}; assert(readBoundedImage(reader,budget).valid); assert(reader.calls==1);
    }
    for (Size dimensions : {Size{4096,4097}, Size{8192,8192}, Size{0,100}, Size{-1,100}, Size{2147483647,2147483647}}) {
        QImageReader reader{dimensions}; assert(!readBoundedImage(reader,budget).valid); assert(reader.calls==0);
    }
    QImageReader desktop{{8192,8192}}; assert(readBoundedImage(desktop,0).valid && desktop.calls==1);
    assert(!decodedImageFits(4294967296LL,1,budget));
    assert(!decodedImageFits(1,4294967296LL,budget));
    assert(!decodedImageFits(-4294967296LL,1,budget));
}
'''.replace("FUNCTION",function)
# Every decoder checks before allocating its decoded raster, including custom codecs.
assert source.count("return readBoundedImage(")==2
for name, allocation in [("TGAReader", "QImage image{"), ("OpenEXRReader", "pixels.resizeErase")]:
    decoder=(ROOT/f"libraries/image/src/image/{name}.cpp").read_text()
    assert decoder.index("decodedImageFits(") < decoder.index(allocation)
network=(ROOT/"libraries/material-networking/src/material-networking/TextureCache.cpp").read_text()
assert 'hasher.addData("ios-image-1mp-decode16mp-v1")' in network
assert "processingPixels = std::min(processingPixels, 1024 * 1024)" in network
with tempfile.TemporaryDirectory(prefix="overte-image-budget-") as tmp:
    path=Path(tmp)/"test.cpp"; path.write_text(code)
    binary=Path(tmp)/"test"
    subprocess.run(["c++","-std=c++17","-include","initializer_list","-I",str(ROOT/"libraries/image/src/image"),str(path),"-o",str(binary)],check=True,timeout=30)
    subprocess.run([str(binary)],check=True,timeout=10)
    # Prove the actual pre-decode check is necessary, not just a passing helper.
    mutant=code.replace("if (!decodedImageFits(size.width(), size.height(), maxDecodedPixels))", "if (false)")
    path.write_text(mutant)
    subprocess.run(["c++","-std=c++17","-include","initializer_list","-I",str(ROOT/"libraries/image/src/image"),str(path),"-o",str(binary)],check=True,timeout=30)
    failed=subprocess.run([str(binary)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert failed.returncode != 0
print("PASS: actual decode boundary accepts valid dimensions, rejects oversized/corrupt dimensions before read, preserves desktop policy; deleted-guard counterexample fails")
