#!/usr/bin/env python3
"""Actual production export branches with real QImage PNG I/O in private scratch."""
import os,pathlib,shlex,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
class DiagnosticImages(unittest.TestCase):
 def test_screen_and_world_diagnostics_do_not_export_pixels(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Gui'],text=True))
  baseline=os.environ.get('OVERTE_IMAGE_EXPORT_BASELINE')
  for path,end in [('interface/src/ui/ApplicationOverlay.cpp','        if (captureSequence >= 0)'),('libraries/entities-renderer/src/RenderableWebEntityItem.cpp','            if (diagnostics.captureSequence >= 0)')]:
   source=(subprocess.check_output(['git','show',baseline+':'+path],cwd=ROOT,text=True) if baseline else (ROOT/path).read_text())
   block='QString capturePath;'+source.split('QString capturePath;',1)[1].split(end,1)[0]
   harness=r'''
#include <QImage>
#include <QDir>
#include <QString>
#include <cassert>
static QString output;
// The path boundary targets test scratch, never the user's real Documents.
struct QStandardPaths { enum { DocumentsLocation }; static QString writableLocation(int){return output;} };
bool iosRuntimeDiagnosticBool(const char*,bool){return true;}
int main(int argc,char**argv){
 assert(argc==2);output=QString::fromLocal8Bit(argv[1]);
 QImage uploadImage(16,16,QImage::Format_RGBA8888);uploadImage.fill(Qt::red);
 // All capture selectors enabled, matching actual screenshot export requests.
 const bool selectedFrame=true,selectedSequence=true,sourceMatches=true;
 const bool selectedOrdinal=true,selectedInterval=true;
 const int _iosQmlFrameOrdinal=1,_softwareFrameOrdinal=1,_geometryId=42;
 struct { bool captureFirstFrame=true; } diagnostics;
 BODY
 assert(capturePath.isEmpty() && !captureSaved);
 assert(QDir(output).entryList(QDir::Files|QDir::NoDotAndDotDot).isEmpty());
 // Retirement must not damage the render image itself.
 assert(uploadImage.pixelColor(0,0)==QColor(Qt::red));
}
'''.replace('BODY',block)
   with self.subTest(path=path),tempfile.TemporaryDirectory(prefix='qml-no-export-') as directory:
    directory=pathlib.Path(directory);code=directory/'test.cpp';code.write_text(harness);binary=directory/'test';out=directory/'documents';out.mkdir()
    subprocess.run(['c++','-std=c++17','-fPIC',str(code),'-o',str(binary),*flags],check=True,timeout=30)
    result=subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(out)],text=True,capture_output=True,timeout=5)
    pngs=[p for p in out.iterdir() if p.is_file() and p.read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a"))]
    self.assertEqual(result.returncode,0,result.stderr+" retained_png_count="+str(len(pngs)))
if __name__=='__main__':unittest.main()
