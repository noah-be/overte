#!/usr/bin/env python3
"""Execute the actual Android bootstrap in a language-free CMake fixture."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / 'android/common/cmake/overte-android-bootstrap.cmake'

class NeutralBootstrap(unittest.TestCase):
    def configure(self, *, host=True, target=True, fdroid=None, wrapper=False):
        with tempfile.TemporaryDirectory(prefix='neutral-bootstrap-') as temp:
            temp = Path(temp)
            hostdir = temp / 'host tools'; hostdir.mkdir()
            graph = temp / 'target graph'; graph.mkdir()
            qt = temp / 'qt'
            header = qt / 'include/QtCore/5.15.18/QtCore/private/qjni_p.h'
            header.parent.mkdir(parents=True); header.write_text('// fixture: no native compilation\n')
            (graph / 'conandeps_legacy.cmake').write_text(f'set(qt_PACKAGE_FOLDER_DEBUG "{qt}")\n')
            selected = BOOTSTRAP.with_name('pico-bootstrap.cmake') if wrapper else BOOTSTRAP
            cmake = 'cmake_minimum_required(VERSION 3.24)\nproject(NeutralBootstrap NONE)\nset(ANDROID TRUE)\n'
            if host: cmake += f'set(HIFI_ANDROID_HOST_TOOLS "{hostdir}")\n'
            if target: cmake += f'set(HIFI_ANDROID_CONAN_GENERATORS "{graph}")\n'
            cmake += f'include("{selected}")\n'
            cmake += '''get_target_property(gl OpenGL::GL INTERFACE_LINK_LIBRARIES)
if(NOT gl STREQUAL "GLESv3")
    message(FATAL_ERROR "wrong GL target")
endif()
foreach(name Qt5::AndroidExtras Qt5::WebView Qt5::WebEngineCore Qt5::WebEngineWidgets)
    if(NOT TARGET ${name})
        message(FATAL_ERROR "missing compatibility target")
    endif()
endforeach()
get_target_property(includes Qt5::AndroidExtras INTERFACE_INCLUDE_DIRECTORIES)
if(NOT includes MATCHES "/android-compat;")
    message(FATAL_ERROR "non-neutral compatibility implementation")
endif()
get_property(pools GLOBAL PROPERTY JOB_POOLS)
if(NOT pools STREQUAL "android_compile=3;android_link=1")
    message(FATAL_ERROR "lost governor")
endif()
include("${CMAKE_BINARY_DIR}/cmake/ConanToolsDirs.cmake")
foreach(tool SCRIBE GLSLANG SPIRV_CROSS SPIRV_TOOLS)
    if(NOT "${${tool}_DIR}" STREQUAL "${EXPECTED_HOST}")
        message(FATAL_ERROR "wrong host graph")
    endif()
endforeach()
'''
            (temp / 'CMakeLists.txt').write_text(cmake)
            env = dict(os.environ, PICO_BUILD_JOBS='3')
            env.pop('OVERTE_FDROID_CONAN_DIR', None)
            expected = hostdir
            if fdroid is not None:
                sourcegraph = temp / 'source graph'; sourcegraph.mkdir()
                env['OVERTE_FDROID_CONAN_DIR'] = '' if fdroid == 'empty' else str(sourcegraph)
                if fdroid == 'valid':
                    expected = sourcegraph / 'linux host'; expected.mkdir()
                    (sourcegraph / 'fdroid-host-tools.cmake').write_text(''.join(
                        f'set(ENV{{{tool}_DIR}} "{expected}")\n'
                        for tool in ['SCRIBE', 'GLSLANG', 'SPIRV_CROSS', 'SPIRV_TOOLS']))
            return subprocess.run(['unshare', '--user', '--map-root-user', '--net',
                'cmake', '-S', str(temp), '-B', str(temp / 'out'), '-G', 'Unix Makefiles',
                '-DEXPECTED_HOST=' + str(expected)], env=env,
                capture_output=True, text=True, timeout=15)

    def test_explicit_prepared_inputs(self):
        result = self.configure(); self.assertEqual(result.returncode, 0, result.stderr)
    def test_compatibility_entry_point_uses_same_implementation(self):
        result = self.configure(wrapper=True); self.assertEqual(result.returncode, 0, result.stderr)
    def test_no_implicit_host_tool_fallback(self):
        result = self.configure(host=False)
        self.assertNotEqual(result.returncode, 0); self.assertIn('HIFI_ANDROID_HOST_TOOLS', result.stderr)
    def test_no_implicit_target_graph_fallback(self):
        result = self.configure(target=False)
        self.assertNotEqual(result.returncode, 0); self.assertIn('HIFI_ANDROID_CONAN_GENERATORS', result.stderr)
    def test_source_built_host_graph_takes_precedence(self):
        result = self.configure(fdroid='valid'); self.assertEqual(result.returncode, 0, result.stderr)
    def test_source_built_host_graph_needs_no_legacy_host(self):
        result = self.configure(host=False, fdroid='valid'); self.assertEqual(result.returncode, 0, result.stderr)
    def test_missing_source_built_graph_does_not_fallback(self):
        result = self.configure(fdroid='missing'); self.assertNotEqual(result.returncode, 0)
        self.assertIn('fdroid-host-tools.cmake', result.stderr)
    def test_empty_source_built_graph_does_not_fallback(self):
        result = self.configure(fdroid='empty'); self.assertNotEqual(result.returncode, 0)
        self.assertIn('must not be empty', result.stderr)
    def test_bound_source_files_match_current_tree(self):
        data = json.loads((ROOT / 'android/phone/fdroid/manifests/recipe-source.lock.json').read_text())
        import hashlib
        bound = next(v for v in data.values() if isinstance(v, dict) and 'android/common/cmake/pico-bootstrap.cmake' in v)
        self.assertIn('android/common/cmake/overte-android-bootstrap.cmake', bound)
        for file, digest in bound.items():
            self.assertEqual(hashlib.sha256((ROOT / file).read_bytes()).hexdigest(), digest, file)

if __name__ == '__main__': unittest.main(verbosity=2)
