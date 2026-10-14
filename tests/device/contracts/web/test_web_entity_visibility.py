#!/usr/bin/env python3
"""Execute complete actual WebEntityRenderer caller bodies with real Qt Quick.

Surface acquisition, entity properties and scene/GPU endpoints are explicit
fixtures. Effective descendant visibility and the shared native document grants
use actual Qt and production policy; this is not an SDK/device/media test.
"""
import os
from pathlib import Path
import shlex
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def body(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class WorldWebVisibility(unittest.TestCase):
    def test_actual_renderer_visibility_and_surface_lifetimes(self):
        qt = os.environ.get('OVERTE_WEB_VISIBILITY_QT', 'Qt6')
        self.assertIn(qt, ('Qt5', 'Qt6'))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', qt+'Core', qt+'Gui', qt+'Quick', qt+'Qml'], text=True))
        if qt == 'Qt5' and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
            flags.insert(0, '-L' + subprocess.check_output(
                ['pkg-config', '--variable=libdir', qt+'Core'], text=True).strip())
        variable = 'host_bins' if qt == 'Qt5' else 'libexecdir'
        moc = Path(subprocess.check_output(
            ['pkg-config', '--variable='+variable, qt+'Core'], text=True).strip()) / 'moc'
        if not moc.is_file() and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
            moc = Path(os.environ['PKG_CONFIG_SYSROOT_DIR']) / str(moc).lstrip('/')
        path = 'libraries/entities-renderer/src/RenderableWebEntityItem.cpp'
        baseline = os.environ.get('OVERTE_WEB_VISIBILITY_BASELINE')
        current = (ROOT / path).read_text()
        source = subprocess.check_output(['git', 'show', baseline+':'+path], cwd=ROOT, text=True) if baseline else current
        signatures = ('WebEntityRenderer::ContentType WebEntityRenderer::getContentType(',
                      'void WebEntityRenderer::doRenderUpdateSynchronousTyped(',
                      'void WebEntityRenderer::buildWebSurface(', 'void WebEntityRenderer::destroyWebSurface(')
        # Baseline retains its original callers, with the newly added API only
        # available as an explicit boundary so failure is runtime, not compile.
        release_baseline = os.environ.get('OVERTE_WEB_VISIBILITY_RELEASE_BASELINE')
        release_source = subprocess.check_output(['git', 'show', release_baseline+':'+path], cwd=ROOT, text=True) if release_baseline else source
        methods = '\n'.join(body(release_source if 'destroyWebSurface' in marker else source, marker)
                            for marker in signatures)
        methods += '\n' + body(current, 'void WebEntityRenderer::synchronizeWebVisibility(')
        header = (ROOT / 'libraries/entities-renderer/src/RenderableWebEntityItem.h').read_text()
        members = '\n'.join(line for line in header.splitlines() if
                            '_webSurfaceLease;' in line or '_webSurfaceVisible ' in line)
        constants_source = source
        constants_baseline = os.environ.get('OVERTE_WEB_PROPERTY_BASELINE')
        if constants_baseline:
            constants_source = subprocess.check_output(['git', 'show', constants_baseline+':'+path], cwd=ROOT, text=True)
        constants = '\n'.join(next(line for line in constants_source.splitlines()
                                   if line.startswith('const char* WebEntityRenderer::'+name+' = '))
                              for name in ('URL_PROPERTY', 'SCRIPT_URL_PROPERTY', 'USE_BACKGROUND_PROPERTY',
                                           'USER_AGENT_PROPERTY', 'GLOBAL_POSITION_PROPERTY'))
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        root_initialization = body(setup, 'auto rootItemLoadedFunctor = [url, webSurface]') + ';'
        # Read the actual property declarations shared by the base and Android
        # world roots. Visual loaders remain covered by embedded-web-qml.
        properties = []
        for relative in ('Web3DSurface.qml', '+android_interface/Web3DSurface.qml'):
            qml = (ROOT / 'interface/resources/qml' / relative).read_text()
            properties.append('\n'.join(line.strip() for line in qml.splitlines()
                              if re.match(r'\s*property (?:string|bool) (?:url|scriptUrl|useBackground|userAgent):', line)))
        self.assertEqual(properties[0], properties[1])
        with tempfile.TemporaryDirectory(prefix='overte-web-entity-visibility-') as temporary:
            stage = Path(temporary)
            (stage / 'production-visibility-methods.inc').write_text(methods)
            (stage / 'production-visibility-members.inc').write_text(members)
            (stage / 'production-visibility-constants.inc').write_text(constants)
            (stage / 'production-acquire-root-initialization.inc').write_text(root_initialization)
            schema = stage / 'ProductionWorldRoot.qml'
            schema.write_text('import QtQuick 2.7\nItem {\n'+properties[0]+'\n}\n')
            fixture = HERE / 'web-entity-visibility-test.cpp'
            subprocess.run([str(moc), str(fixture), '-o', str(stage / 'web-entity-visibility-test.moc')], check=True, timeout=30)
            binary = stage / 'visibility'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-fPIC', '-pthread',
                            '-I'+str(ROOT), '-I'+str(stage), str(fixture), '-o', str(binary), *flags], check=True, timeout=60)
            subprocess.run([str(binary), str(schema)], check=True, timeout=15, env=os.environ | {
                'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'})


if __name__ == '__main__':
    unittest.main()
