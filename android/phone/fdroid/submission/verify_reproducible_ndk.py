# SPDX-License-Identifier: Apache-2.0
"""Opt-in integration regression: requires Conan 2.25.2, GCC 14 and ANDROID_NDK_HOME. No Android app build or downloads."""
import os, pathlib, subprocess, hashlib, json, shutil
import tempfile
workspace = tempfile.TemporaryDirectory(prefix='overte-repro-')
root=pathlib.Path(workspace.name)
source=pathlib.Path(__file__).resolve().parents[4]
fixture=root/'fixture';fixture.mkdir()
(fixture/'conanfile.py').write_text('''from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain
from conan.tools.files import copy
class Probe(ConanFile):
 name="repro-probe"
 version="1.0"
 settings="os", "arch", "compiler", "build_type"
 exports_sources="CMakeLists.txt", "probe.cpp"
 def generate(self): CMakeToolchain(self).generate()
 def build(self):
  cm=CMake(self);cm.configure();cm.build()
 def package(self): copy(self,"libprobe.so",self.build_folder,self.package_folder)
''')
(fixture/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(probe CXX)\nadd_library(probe SHARED probe.cpp)\n')
(fixture/'probe.cpp').write_text('extern "C" const char *source_file() { return __FILE__; }\nextern "C" const char *date() { return __DATE__ " " __TIME__; }\n')
results=[]
for name in ['first','second-longer-path']:
 attempt=root/name;attempt.mkdir();env=dict(os.environ,CONAN_HOME=str(attempt/'cache'),OVERTE_ATTEMPT_ROOT=str(attempt),OVERTE_FDROID_STANDARD_TOOLCHAIN='1',SOURCE_DATE_EPOCH='1790000000',CMAKE_GENERATOR='Ninja')
 hooks=attempt/'cache/extensions/hooks';hooks.mkdir(parents=True)
 shutil.copy(source/'android/phone/fdroid/submission/hook_reproducible.py',hooks/'hook_reproducible.py')
 cmd=['conan','create',str(fixture),'--no-remote','--build=*','-pr:h',str(source/'android/phone/fdroid/conan/profiles/android-arm64-v8a-api26-16k'),'-pr:b',str(source/'android/phone/fdroid/conan/profiles/linux-x86_64-bootstrap'),'-s:h','compiler.version=18','-s:b','compiler.version=14','-c','tools.cmake.cmaketoolchain:generator=Ninja','--format=json']
 data=json.loads(subprocess.check_output(cmd,env=env,text=True))
 node=next(n for n in data['graph']['nodes'].values() if (n.get('ref') or '').startswith('repro-probe/'))
 p=next(pathlib.Path(node['package_folder']).rglob('libprobe.so'));binary=p.read_bytes();results.append(binary)
 assert bytes(str(attempt),'utf-8') not in binary, 'random build path survived in Android ELF'
print('Two real NDK/Conan builds in different caches:',hashlib.sha256(results[0]).hexdigest(),hashlib.sha256(results[1]).hexdigest())
assert results[0]==results[1]
