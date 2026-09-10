# SPDX-License-Identifier: Apache-2.0
"""Compile the original backend-selection body against narrow Qt substitutes."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]


class ProducerBoundaryTests(unittest.TestCase):
    def test_inventory_matches_actual_producer_and_two_image_consumers(self):
        anchors = {
            'interface/src/Application_Graphics.cpp': 'SharedGraphicsContext::Backend::Software',
            'libraries/qml/src/qml/impl/SharedObject.cpp': 'QQuickWindow::setGraphicsApi(QSGRendererInterface::Software)',
            'libraries/qml/src/qml/impl/RenderEventHandler.cpp': 'QQuickRenderTarget::fromPaintDevice(&_softwareImage)',
            'interface/src/ui/ApplicationOverlay.cpp': 'offscreenUI->fetchImage(sourceImage)',
            'libraries/entities-renderer/src/RenderableWebEntityItem.cpp': '_webSurface->fetchImage(newImage)',
            'libraries/vk/src/vk/VKWindow.cpp': '_swapchain.initSurface(metalLayer)',
        }
        for relative, anchor in anchors.items():
            self.assertIn(anchor, (ROOT/relative).read_text(), relative)

    def test_original_context_selection_four_platform_version_combinations(self):
        source = (ROOT/'libraries/qml/src/qml/OffscreenSurface.cpp').read_text()
        body = source.split('bool OffscreenSurface::configureSharedGraphicsContext(const SharedGraphicsContext& context) {',1)[1].split('\n}',1)[0]
        harness = '''
#include <cassert>
#define QT_VERSION_CHECK(a,b,c) ((a)*65536+(b)*256+(c))
struct QOpenGLContext {};
int softwareCalls = 0, glCalls = 0;
struct SharedObject { static void setSoftwareRendering() { ++softwareCalls; } };
struct OffscreenSurface {
  struct SharedGraphicsContext {
    enum class Backend { Unsupported, OpenGL, Software };
    Backend backend; void* handle;
  };
  static void setSharedContext(QOpenGLContext*) { ++glCalls; }
  static bool configureSharedGraphicsContext(const SharedGraphicsContext& context) { BODY
  }
};
int main() {
  using Context = OffscreenSurface::SharedGraphicsContext;
  using Backend = Context::Backend;
  assert(!OffscreenSurface::configureSharedGraphicsContext({Backend::Unsupported, nullptr}));
  assert(!OffscreenSurface::configureSharedGraphicsContext({Backend::OpenGL, nullptr}));
  bool software = OffscreenSurface::configureSharedGraphicsContext({Backend::Software, nullptr});
  assert(software == (QT_VERSION >= QT_VERSION_CHECK(6,0,0)));
  assert(softwareCalls == (software ? 1 : 0));
  QOpenGLContext gl;
  bool accepted = OffscreenSurface::configureSharedGraphicsContext({Backend::OpenGL, &gl});
#if defined(Q_OS_IOS)
  assert(!accepted && glCalls == 0);
#else
  assert(accepted && glCalls == 1);
#endif
}
'''.replace('BODY', body)
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary)/'producer.cpp'; path.write_text(harness)
            for version in (5,6):
                for ios in (False,True):
                    with self.subTest(version=version,ios=ios):
                        binary = pathlib.Path(temporary)/('producer-%s-%s'%(version,ios))
                        flags = ['-DQ_OS_IOS'] if ios else []
                        subprocess.run(['c++','-std=c++14','-Wall','-Wextra','-Werror',
                            '-DQT_VERSION=%s'%(version*65536),*flags,str(path),'-o',str(binary)],
                            check=True,timeout=30)
                        subprocess.run([str(binary)],check=True,timeout=5)

    def test_direct_legacy_gl_entries_fail_closed_on_ios(self):
        source = (ROOT/'libraries/qml/src/qml/impl/SharedObject.cpp').read_text()
        for method, marker in [('setSharedContext','OVT_IOS_QML_GL_CONTEXT_UNSUPPORTED'),
                               ('setRenderTarget','OVT_IOS_QML_GL_TARGET_UNSUPPORTED')]:
            body = source.split('void SharedObject::'+method+'(',1)[1].split('\n}',1)[0]
            ios = body.split('#if defined(Q_OS_IOS)',1)[1].split('#else',1)[0]
            self.assertIn('qFatal("'+marker+'")', ios)
            self.assertNotIn('fromOpenGL',ios)
            self.assertNotIn('setProperty',ios)


if __name__ == '__main__': unittest.main()
