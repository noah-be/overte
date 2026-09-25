# SPDX-License-Identifier: Apache-2.0
"""Opt-in Qt5/qmake reproducibility regression; builds two tiny libraries only."""
import os,subprocess,tempfile,pathlib,hashlib,importlib.util
from types import SimpleNamespace
p=pathlib.Path(__file__).with_name('hook_reproducible.py')
spec=importlib.util.spec_from_file_location('hook',p);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
qmake=os.environ.get('QMAKE', '/usr/lib/qt5/bin/qmake')
data=pathlib.Path(subprocess.check_output([qmake,'-query','QT_HOST_DATA'],text=True).strip())
results=[]
with tempfile.TemporaryDirectory() as td:
 for name in ['first','second-longer']:
  r=pathlib.Path(td)/name;r.mkdir();features=r/'qt5/qtbase/mkspecs/features';features.mkdir(parents=True)
  (features/'default_post.prf').write_text((data/'mkspecs/features/default_post.prf').read_text())
  recipe=SimpleNamespace(name='qt',ref='qt/5.15.18@overte/stable',source_folder=str(r),build_folder=str(r),package_folder=str(r/'p'),generators_folder=str(r),dependencies={})
  os.environ['OVERTE_FDROID_STANDARD_TOOLCHAIN']='1';h.post_generate(recipe)
  (r/'probe.cpp').write_text('extern "C" const char* filename() { return __FILE__; }\n')
  (r/'probe.pro').write_text('TEMPLATE=lib\nCONFIG-=qt\nCONFIG+=plugin\nTARGET=probe\nSOURCES='+str(r/'probe.cpp')+'\n')
  env=dict(os.environ,QMAKEFEATURES=str(features),SOURCE_DATE_EPOCH='1790000000')
  subprocess.run([qmake,str(r/'probe.pro')],cwd=r,env=env,check=True)
  subprocess.run(['make','-j2'],cwd=r,env=env,check=True)
  b=(r/'libprobe.so').read_bytes(); assert str(r).encode() not in b
  results.append(b)
print('Qt5 qmake default_post regression:',*[hashlib.sha256(b).hexdigest() for b in results])
assert results[0]==results[1]
