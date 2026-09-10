#!/usr/bin/env python3
"""Compile actual modal listeners with real Qt items/signals and an owner seam."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def block(text, start):
    begin = text.index(start)
    left = text.index('{', begin)
    depth = 1
    end = left + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[begin:end]


class ModalCompletionTest(unittest.TestCase):
    def test_actual_listeners(self):
        cpp = (ROOT / 'libraries/ui/src/OffscreenUi.cpp').read_text()
        header = (ROOT / 'libraries/ui/src/OffscreenUi.h').read_text()
        base = block(header, 'class ModalDialogListener :') + ';'
        classes = '\n'.join(block(cpp, 'class ' + name + ' :') + ';' for name in (
            'MessageBoxListener', 'InputDialogListener', 'FileDialogListener', 'AssetDialogListener'))
        functions = '\n'.join(block(cpp, signature) for signature in (
            'void OffscreenUi::removeModalDialog(', 'void OffscreenUi::registerModalDialog(',
            'ModalDialogListener::ModalDialogListener(', 'ModalDialogListener::~ModalDialogListener(',
            'QVariant ModalDialogListener::waitForResult(', 'void ModalDialogListener::finish(',
            'void ModalDialogListener::onDestroyed(', 'QString OffscreenUi::getText(const Icon',
            'QString OffscreenUi::getItem(const Icon', 'QVariant OffscreenUi::waitForInputDialogResult(',
            'ModalDialogListener* OffscreenUi::getItemAsync(const Icon')
            if signature in cpp)
        harness = (Path(__file__).with_name('modal-dialog-completion-test.cpp')).read_text()
        source = harness.replace('// ACTUAL_BASE', base).replace('// ACTUAL_CLASSES', classes).replace('// ACTUAL_FUNCTIONS', functions)
        if os.environ.get('OVERTE_MODAL_EARLY_TEXT_CONVERSION'):
            source = source.replace('inputDialog(icon, title, label, text);', 'inputDialog(icon, title, label, text).toString();')
        if os.environ.get('OVERTE_MODAL_CANCEL_AS_TEXT'):
            source = source.replace('void onCanceled() {\n        finish(QVariant());', 'void onCanceled() {\n        finish(QString());')
        if os.environ.get('OVERTE_MODAL_DUPLICATE_RESPONSE'):
            source = source.replace('if (_finished) { return; }', '')
            source = source.replace('disconnect(_dialog, nullptr, this, nullptr);', '')
        if os.environ.get('OVERTE_MODAL_DROP_NULL_RESPONSE'):
            source = source.replace('QTimer::singleShot(0, this, [this] { onDestroyed(); });', '')
        with tempfile.TemporaryDirectory(prefix='overte-modal-') as temp:
            temp = Path(temp)
            path = temp / 'test.cpp'
            path.write_text(source)
            subprocess.run(['/usr/lib64/qt6/libexec/moc', str(path), '-o', str(temp / 'test.moc')], check=True)
            flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Quick', 'Qt6Widgets'], text=True))
            subprocess.run(['g++', '-std=c++17', '-fPIC', str(path), '-o', str(temp / 'test'), *flags], check=True, timeout=90)
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(temp / 'test')], env=env, check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
