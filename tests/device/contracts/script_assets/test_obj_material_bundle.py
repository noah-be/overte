#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Execute actual OBJ tokenizer/group/MTL/request bodies with real Qt files and GLM.

ResourceManager providers and HFM storage are explicit host boundaries. No renderer or live server.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).resolve().parent
qt = Path(os.environ.get('OVERTE_QT5_ROOT', str(Path.home() / '.local/overte-qt5/root')))
qt5_available = (qt / 'usr/lib64/pkgconfig/Qt5Core.pc').is_file() or subprocess.run(
    ['pkg-config', '--exists', 'Qt5Core'], check=False).returncode == 0
major = os.environ.get('OVERTE_NATIVE_QT_MAJOR', '5' if qt5_available else '6')
assert major in ('5', '6')
environment = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
    'QT_LOGGING_RULES': '*.warning=true;*.info=false',
    'OVERTE_QML_SOURCE_ROOT': str(ROOT / 'interface/resources/qml')}
libraries = []
if major == '5' and (qt / 'usr/lib64/pkgconfig/Qt5Core.pc').is_file():
    environment.update({'PKG_CONFIG_PATH': str(qt / 'usr/lib64/pkgconfig'), 'PKG_CONFIG_SYSROOT_DIR': str(qt),
        'LD_LIBRARY_PATH': str(qt / 'usr/lib64'), 'QML2_IMPORT_PATH': str(qt / 'usr/lib64/qt5/qml'),
        'QT_PLUGIN_PATH': str(qt / 'usr/lib64/qt5/plugins')})
    tools = qt / 'usr/lib64/qt5/bin'
    libraries = ['-L' + str(qt / 'usr/lib64')]
else:
    tools = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir' if major == '6' else '--variable=host_bins', 'Qt' + major + 'Core'], env=environment, text=True).strip())
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs',
    *['Qt' + major + name for name in ('Core', 'Gui')]], env=environment, text=True))

glm = os.environ.get('OVERTE_TEST_GLM_INCLUDE')
glm_flags = ['-isystem', glm] if glm else []

def body(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

with tempfile.TemporaryDirectory(prefix='overte-obj-material-') as temporary:
    stage = Path(temporary)
    header = (ROOT / 'libraries/model-serializers/src/OBJSerializer.h').read_text()
    cpp = (ROOT / 'libraries/model-serializers/src/OBJSerializer.cpp').read_text()
    declarations = header[header.index('class OBJTokenizer {'):header.index('class OBJSerializer:')]
    (stage / 'obj-declarations.inc').write_text(declarations)
    fields = header[header.index('    typedef QVector<OBJFace> FaceGroup;'):header.index('    HFMModel::Pointer read(')]
    (stage / 'obj-fields.inc').write_text(fields)
    names = ('parseOBJGroup', 'loadMaterialLibraries', 'parseMaterialLibrary', 'parseTextureLine', 'isValidTexture')
    methods = []
    for name in names:
        methods.append(re.search(r'(?:bool|void) '+name+r'\([^;]+;', header).group())
    methods.append(re.search(r'HFMModel::Pointer read\([^;]+;', header).group().replace(' override', ''))
    (stage / 'obj-methods.inc').write_text('\n'.join(methods))
    hfm = (ROOT / 'libraries/hfm/src/hfm/HFM.h').read_text()
    values = hfm[hfm.index('class Texture {'):hfm.index('/// A single mesh')]
    values = values.replace('class Texture {', 'class HFMTexture {').replace('    Texture ', '    HFMTexture ')
    values = values.replace('class MeshPart {', 'class HFMMeshPart {').replace('class Material {', 'class HFMMaterial {')
    values = values.replace('    Material(', '    HFMMaterial(')
    constant = re.search(r'const int MAX_NUM_PIXELS_FOR_FBX_TEXTURE = [^;]+;', hfm).group()
    (stage / 'obj-hfm-values.inc').write_text(constant+'\n'+values)
    tokenizer = cpp[cpp.index('OBJTokenizer::OBJTokenizer('):cpp.index('void setMeshPartDefaults(')]
    faces = cpp[cpp.index('void setMeshPartDefaults('):cpp.index('bool OBJSerializer::isValidTexture(')]
    parser = body(cpp, 'bool OBJSerializer::parseOBJGroup(')
    bodies = [body(cpp, signature) for signature in (
        'void OBJSerializer::parseMaterialLibrary(', 'void OBJSerializer::parseTextureLine(',
        'std::tuple<bool, hifi::ByteArray> requestData(', 'void OBJSerializer::loadMaterialLibraries(',
        'bool OBJSerializer::isValidTexture(', 'HFMModel::Pointer OBJSerializer::read(')]
    constants = cpp[cpp.index('QHash<QString, float> COMMENT_SCALE_HINTS'):cpp.index('OBJTokenizer::OBJTokenizer(')]
    (stage / 'obj-body.inc').write_text(constants+tokenizer+faces+'\n'+'\n'.join(bodies)+'\n'+parser+'\n'+body((ROOT/'libraries/procedural/src/procedural/ProceduralMaterialCache.cpp').read_text(), 'QUrl NetworkMaterial::getTextureUrl('))
    subprocess.run([str(tools / 'moc'), str(FIXTURES / 'obj-material-services.h'), '-o', str(stage / 'moc.cpp')], check=True)
    binary = stage / 'obj-material'
    subprocess.run(['c++', '-std=c++17', '-fPIC', '-UNDEBUG', *glm_flags, str(FIXTURES / 'obj-material.cpp'),
        str(stage / 'moc.cpp'), '-I'+str(stage), '-I'+str(FIXTURES), '-I'+str(ROOT / 'libraries/shared/src'), '-I'+str(ROOT / 'libraries/image/src'),
        *libraries, '-o', str(binary), *flags], env=environment, check=True, timeout=90)
    subprocess.run([str(binary)], env=environment, check=True, timeout=30)
