#!/usr/bin/env python3
"""Compile the real KTX header/size producer with the iOS allocation gate."""
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
package=next((p for p in ['Qt6Core','Qt5Core'] if subprocess.run(['pkg-config','--exists',p]).returncode==0),None)
if not package:
    raise SystemExit('Qt Core development files required for KTX producer regression')
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',package],text=True))
code=r'''
#include <cassert>
#include <ktx/KTX.h>
#include "KtxAllocationBudget.h"
int main() {
    constexpr uint64_t MiB=1024ULL*1024;
    ktx::Header h; h.set2D(4096,4096); h.numberOfMipmapLevels=13;
    auto bytes=image::checkedKtxPlaceholderBytes(h);
    assert(bytes>85*MiB && bytes<86*MiB);
    ktx::Byte mip=13;
    ktx::KeyValues keys{ktx::KeyValue(ktx::HIFI_MIN_POPULATED_MIP_KEY,1,&mip)};
    auto actual=ktx::KTX::evalStorageSize(h,h.generateImageDescriptors(),keys);
    assert(bytes>=actual && bytes-actual<64);
    assert(image::ktxPlaceholderFits(bytes,1024*MiB));
    assert(!image::ktxPlaceholderFits(bytes,550*MiB));
    assert(!image::ktxPlaceholderFits(bytes,0));
    assert(!image::ktxPlaceholderFits(0,1024*MiB));
    h.set2D(8192,8192); h.numberOfMipmapLevels=14;
    bytes=image::checkedKtxPlaceholderBytes(h);
    assert(bytes>341*MiB && bytes<342*MiB);
    assert(!image::ktxPlaceholderFits(bytes,8*1024*MiB));
    h.setCube(4096,4096); h.numberOfMipmapLevels=13;
    bytes=image::checkedKtxPlaceholderBytes(h);
    actual=ktx::KTX::evalStorageSize(h,h.generateImageDescriptors(),keys);
    assert(bytes>=actual && bytes-actual<64);
    assert(!image::ktxPlaceholderFits(bytes,8*1024*MiB));
    for (uint32_t value: {0u,16u,32u,4294967295u}) {
        h.numberOfMipmapLevels=value; assert(!image::checkedKtxPlaceholderBytes(h));
    }
    h.numberOfMipmapLevels=13; h.pixelWidth=4294967295u;
    assert(!image::checkedKtxPlaceholderBytes(h));
    h.pixelWidth=4096; h.numberOfFaces=4294967295u;
    assert(!image::checkedKtxPlaceholderBytes(h));
    h.numberOfFaces=1; h.numberOfArrayElements=4294967295u;
    assert(!image::checkedKtxPlaceholderBytes(h));
}
'''
source=(ROOT/'libraries/material-networking/src/material-networking/TextureCache.cpp').read_text()
start=source.index('const auto placeholderBytes =')
assert start < source.index('auto imageDescriptors = header->generateImageDescriptors()',start)
start=source.index('std::unique_lock<std::mutex> placeholderLock')
assert start < source.index('os_proc_available_memory()',start) < source.index('image::ktxPlaceholderFits(',start) < source.index('ktx::KTX::createBare(',start)
with tempfile.TemporaryDirectory(prefix='overte-ktx-budget-') as tmp:
    cpp=Path(tmp)/'test.cpp'; cpp.write_text(code); binary=Path(tmp)/'test'
    command=['c++','-std=c++17','-fPIC','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',str(cpp),str(ROOT/'libraries/ktx/src/ktx/KTX.cpp'),str(ROOT/'libraries/ktx/src/ktx/Writer.cpp'),'-I'+str(ROOT/'libraries/ktx/src'),'-I'+str(ROOT/'libraries/shared/src'),'-I'+str(ROOT/'libraries/material-networking/src/material-networking'),'-o',str(binary)]+flags
    subprocess.run(command,check=True,timeout=40)
    subprocess.run([str(binary)],check=True,timeout=10)
print('PASS: real KTX size accounting; 4K conditional admission, 8K/cube rejection, malformed fields, fresh headroom and serialized allocation boundary')
