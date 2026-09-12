#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
"""Actual Qt pool ABA reproduction, patched interleaving and concurrent ownership.

Host Qt is used for atomic primitives, not as proof of native iOS acceptance.
"""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('patch', ROOT / 'ios/tools/qt-mutex-patch.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
FIXTURES = Path(__file__).parent / 'fixtures/qt-6.11.1'

CPP = r'''
#include <QtCore/qglobal.h>
#include <QtCore/qatomic.h>
#include <atomic>
#include <future>
#include <thread>
#include <mutex>
#include <cassert>
#include <set>
#include <vector>
#include <iostream>
std::atomic<bool> hold{false}; std::promise<void> entered, resume;
std::shared_future<void> resumed = resume.get_future();
void pauseNext() { if (hold.exchange(false)) { entered.set_value(); resumed.wait(); } }
#include "qfreelist_p.h"
struct QMutexPrivate {
    QAtomicInt refCount{0}, waiters{0}, possiblyUnlocked{0}; int id = 0;
    static QMutexPrivate* allocate(); void release();
};
// The iOS branch is enabled after including host Qt platform headers.
#define Q_OS_IOS
/* POOL */
void retire(QMutexPrivate* item) { item->refCount.storeRelaxed(0); item->release(); }
int main() {
    auto initial = QMutexPrivate::allocate(); retire(initial);
    hold = true;
    QMutexPrivate *a = nullptr, *ownedB = nullptr;
    std::thread reader([&] { a = QMutexPrivate::allocate(); });
    entered.get_future().wait();
    std::promise<void> ready; auto completed = ready.get_future();
    std::thread recycler([&] {
        auto otherA = QMutexPrivate::allocate(); ownedB = QMutexPrivate::allocate();
        retire(otherA);
        for (int i = 0; i < 127; ++i) { auto item = QMutexPrivate::allocate(); retire(item); }
        ready.set_value();
    });
    if (EXPECT_DUPLICATE) {
        assert(completed.wait_for(std::chrono::seconds(5)) == std::future_status::ready);
    } else {
        assert(completed.wait_for(std::chrono::milliseconds(100)) == std::future_status::timeout);
    }
    resume.set_value(); reader.join(); recycler.join();
    auto next = QMutexPrivate::allocate();
    assert((next == ownedB) == bool(EXPECT_DUPLICATE));
    std::cout << "duplicate_live_entry=" << (next == ownedB) << " serial_wrap=128\n";
    if (EXPECT_DUPLICATE) return 0; // The unpatched pool is now corrupt.
    retire(a); retire(ownedB); retire(next);
    std::mutex liveMutex; std::set<QMutexPrivate*> live; std::vector<std::thread> workers;
    for (int t = 0; t < 8; ++t) workers.emplace_back([&] {
        for (int i = 0; i < 10000; ++i) {
            auto item = QMutexPrivate::allocate();
            { std::lock_guard<std::mutex> lock(liveMutex); assert(live.insert(item).second); }
            if (i % 16 == 0) std::this_thread::yield();
            { std::lock_guard<std::mutex> lock(liveMutex); assert(live.erase(item) == 1); }
            retire(item);
        }
    });
    for (auto &worker : workers) worker.join();
    assert(live.empty());
    std::cout << "concurrent_allocations=80000 duplicate_owners=0\n";
}
'''


class PatchTest(unittest.TestCase):
    def source_tree(self, root):
        source = root / patch.SOURCE
        source.parent.mkdir(parents=True)
        source.write_bytes((FIXTURES / 'qmutex.cpp').read_bytes())
        return source

    def test_patch_is_exact_idempotent_and_rejects_foreign_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source_tree(root)
            patch.apply(root)
            self.assertEqual(patch.digest(source), patch.PATCHED)
            patch.apply(root)
            source.write_text(source.read_text() + '// unknown change\n')
            with self.assertRaises(ValueError):
                patch.apply(root)

    def test_receipt_rejects_old_missing_or_changed_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source_tree(root)
            prefix = root / 'sdk'; (prefix / 'lib').mkdir(parents=True)
            archive = prefix / 'lib/libQt6Core.a'; archive.write_bytes(b'!<arch>\ntest fixture')
            plan = prefix / '.overte-qt-ios-plan-id'
            plan.write_text('qt-6.11.1-mutex-' + patch.digest(patch.PATCH))
            with self.assertRaises(FileNotFoundError):
                patch.verify(prefix)
            with self.assertRaises(ValueError):
                patch.seal(root, prefix)
            patch.apply(root); patch.seal(root, prefix); patch.verify(prefix)
            archive.write_bytes(archive.read_bytes() + b'changed')
            with self.assertRaises(ValueError):
                patch.verify(prefix)
            plan.write_text('legacy-unpatched-plan')
            with self.assertRaises(ValueError):
                patch.verify(prefix)

    def test_actual_pool_interleaving_and_stress(self):
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = self.source_tree(root)
            (root / 'QtCore/private').mkdir(parents=True)
            # Ubuntu's Qt 6.4 has the same atomic API but predates this
            # unreachable-return convenience macro. Keep the pinned algorithm
            # unchanged; provide the equivalent in the private-header seam.
            old_macro_test = '#undef Q_UNREACHABLE_RETURN\n' if os.environ.get('OVERTE_TEST_OLD_QT_MACROS') else ''
            (root / 'QtCore/private/qglobal_p.h').write_text(
                '#include <QtCore/qglobal.h>\n#define Q_AUTOTEST_EXPORT\n' + old_macro_test +
                '#ifndef Q_UNREACHABLE_RETURN\n'
                '#define Q_UNREACHABLE_RETURN(...) do { Q_UNREACHABLE(); return __VA_ARGS__; } while (false)\n'
                '#endif\n')
            header = (FIXTURES / 'qfreelist_p.h').read_text()
            anchor = '        newid = v[at].next.loadRelaxed() | (id & ~ConstantsType::IndexMask);'
            self.assertEqual(header.count(anchor), 1)
            (root / 'qfreelist_p.h').write_text(header.replace(anchor, anchor + '\n        pauseNext();'))
            for corrected, ios in [(False, True), (True, True), (True, False)]:
                if corrected:
                    patch.apply(root)
                qt = source.read_text(); start = qt.index('namespace {\nstruct FreeListConstants')
                end = qt.index('// atomically subtract', start)
                fixture = CPP.replace('/* POOL */', qt[start:end])
                if not ios:
                    fixture = fixture.replace('#define Q_OS_IOS', '// Unchanged host branch')
                (root / 'test.cpp').write_text(fixture)
                subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-DQT_NO_DEBUG', '-I' + str(root),
                                '-DEXPECT_DUPLICATE=' + str(int(not (corrected and ios))),
                                str(root / 'test.cpp'), '-o', str(root / 'test'), *flags],
                               check=True, timeout=30)
                subprocess.run([str(root / 'test')], check=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
