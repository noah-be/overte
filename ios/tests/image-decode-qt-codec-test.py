#!/usr/bin/env python3
"""Run the production pre-decode boundary against real Qt PNG/JPEG readers."""
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
package=next((p for p in ['Qt6Gui','Qt5Gui'] if subprocess.run(['pkg-config','--exists',p]).returncode==0),None)
if not package:
    raise SystemExit('Qt Gui development files required for real-codec regression')
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',package],text=True))
source=(ROOT/'libraries/image/src/image/TextureProcessing.cpp').read_text()
function=source[source.index('Image readBoundedImage('):source.index('\nImage processRawImageData')]
code=r'''
#include <cassert>
#include <QBuffer>
#include <QImage>
#include <QImageReader>
#include <QLoggingCategory>
#include "DecodeLimits.h"
Q_LOGGING_CATEGORY(imagelogging,"overte.test.image")
using Image=QImage;
using image::decodedImageFits;
struct TrackingReader:QImageReader {
    using QImageReader::QImageReader;
    unsigned calls=0;
    QImage read(){++calls;return QImageReader::read();}
};
#define QImageReader TrackingReader
FUNCTION
int main() {
    for (const char* format : {"PNG","JPEG"}) {
        for (bool oversized : {false,true}) {
            QImage original(oversized?1025:1024,1024,QImage::Format_RGB32);
            original.fill(0xff184050);
            QByteArray bytes; QBuffer encoded(&bytes); encoded.open(QIODevice::WriteOnly);
            assert(original.save(&encoded,format)); encoded.close(); original=QImage();
            QBuffer input(&bytes); input.open(QIODevice::ReadOnly);
            TrackingReader reader(&input,format); assert(reader.canRead());
            Image result=readBoundedImage(reader,1024ULL*1024);
            assert(reader.calls==(oversized?0u:1u)); assert(result.isNull()==oversized);
            if(!oversized) { assert(result.size()==QSize(1024,1024)); }
        }
    }
}
'''.replace('FUNCTION',function)
with tempfile.TemporaryDirectory(prefix='overte-qt-decode-') as tmp:
    cpp=Path(tmp)/'test.cpp';cpp.write_text(code); binary=Path(tmp)/'test'
    subprocess.run(['c++','-std=c++17','-fPIC',str(cpp),'-I'+str(ROOT/'libraries/image/src/image'),'-o',str(binary)]+flags,check=True,timeout=40)
    subprocess.run([str(binary)],check=True,timeout=20)
print('PASS: actual '+package+' PNG and JPEG decode accepted within budget; oversized images rejected before reader.read()')
