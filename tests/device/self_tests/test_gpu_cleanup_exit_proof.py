#!/usr/bin/env python3
"""No-process/no-signal regressions for fail-closed GPU group cleanup."""
from __future__ import annotations
import errno
import importlib.util
from pathlib import Path
import signal
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'adapters/desktop_oculix/gpu_headless.py'
SPEC = importlib.util.spec_from_file_location('gpu_cleanup_exit_under_test', MODULE)
GPU = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GPU)

PID = 991991
ROOT = {'pid': PID, 'processGroup': PID, 'processToken': '100'}
CHILD = {'pid': PID + 1, 'processGroup': PID, 'processToken': '101'}
DETAILS = ('100', PID, 1, '/owned/image', ('/owned/image',))
CHILD_DETAILS = ('101', PID, PID, '/owned/child', ('/owned/child',))

def kernel_stat(pid: int, state: str) -> str:
    return f'{pid} (owned (nested) name) {state} ' + ' '.join(['1'] * 18 + ['100'])

class ExitProof(unittest.TestCase):
    def test_absence_and_kernel_esrch_are_confirmed(self):
        for error in (FileNotFoundError(errno.ENOENT, 'gone'), ProcessLookupError(errno.ESRCH, 'gone')):
            with self.subTest(error=type(error).__name__), patch.object(GPU.Path, 'read_text', side_effect=error):
                self.assertTrue(GPU._process_confirmed_exited(PID))

    def test_valid_zombie_or_dead_kernel_state_is_confirmed(self):
        for state in ('Z', 'X'):
            with self.subTest(state=state), patch.object(GPU.Path, 'read_text', return_value=kernel_stat(PID, state)):
                self.assertTrue(GPU._process_confirmed_exited(PID))

    def test_permission_io_and_other_os_errors_are_never_exit(self):
        for error in (PermissionError(errno.EACCES, 'denied'), OSError(errno.EIO, 'I/O'), OSError(errno.EINTR, 'interrupted'), UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid')):
            with self.subTest(error=type(error).__name__), patch.object(GPU.Path, 'read_text', side_effect=error):
                self.assertFalse(GPU._process_confirmed_exited(PID))

    def test_live_and_stopped_states_are_never_exit(self):
        for state in ('R', 'S', 'D', 'T', 't', 'I'):
            with self.subTest(state=state), patch.object(GPU.Path, 'read_text', return_value=kernel_stat(PID, state)):
                self.assertFalse(GPU._process_confirmed_exited(PID))

    def test_malformed_or_wrong_pid_stat_is_never_exit(self):
        for value in ('broken', f'{PID} (x) Z 1', kernel_stat(PID + 1, 'Z'), kernel_stat(PID, 'Z')[:-3] + 'NaN'):
            with self.subTest(value=value), patch.object(GPU.Path, 'read_text', return_value=value):
                self.assertFalse(GPU._process_confirmed_exited(PID))

    def test_invalid_pid_never_inspects_proc(self):
        with patch.object(GPU.Path, 'read_text') as read:
            for pid in (True, False, 0, 1, -1, '991991'):
                self.assertFalse(GPU._process_confirmed_exited(pid))
            read.assert_not_called()

class ExitSettling(unittest.TestCase):
    def test_actual_exe_disappearance_can_precede_kernel_zombie_state(self):
        # Execute actual _process_details and actual positive exit checks. Only
        # kernel file I/O is injected; no process or signal is created.
        with patch.object(GPU.Path, 'read_text', side_effect=[kernel_stat(PID, 'R'), kernel_stat(PID, 'S'), kernel_stat(PID, 'Z')]), \
                patch.object(GPU.os, 'readlink', side_effect=FileNotFoundError()), \
                patch.object(GPU.time, 'monotonic', side_effect=[0, 0]), \
                patch.object(GPU.time, 'sleep') as sleep:
            self.assertIsNone(GPU._process_details(PID))
            self.assertTrue(GPU._wait_for_confirmed_exit(PID))
            sleep.assert_called_once_with(0.01)

    def test_still_live_missing_exe_never_becomes_exit_at_deadline(self):
        with patch.object(GPU.Path, 'read_text', return_value=kernel_stat(PID, 'S')), \
                patch.object(GPU.time, 'monotonic', side_effect=[0, 0, 0.25]), \
                patch.object(GPU.time, 'sleep') as sleep:
            self.assertFalse(GPU._wait_for_confirmed_exit(PID))
            sleep.assert_called_once_with(0.01)

    def test_unreadable_or_io_error_never_becomes_exit_at_deadline(self):
        for error in (PermissionError(), OSError(errno.EIO, 'failed')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(GPU.Path, 'read_text', side_effect=error), \
                    patch.object(GPU.time, 'monotonic', side_effect=[0, 0, 0.25]), \
                    patch.object(GPU.time, 'sleep'):
                self.assertFalse(GPU._wait_for_confirmed_exit(PID))

    def test_positive_absence_needs_no_wait_or_clock(self):
        with patch.object(GPU.Path, 'read_text', side_effect=FileNotFoundError()), \
                patch.object(GPU.time, 'monotonic') as clock, \
                patch.object(GPU.time, 'sleep') as sleep:
            self.assertTrue(GPU._wait_for_confirmed_exit(PID))
            clock.assert_not_called()
            sleep.assert_not_called()

class CleanupProof(unittest.TestCase):
    def setUp(self):
        self.lifecycle = object.__new__(GPU.GpuHeadlessLifecycle)
        self.group = patch.object(self.lifecycle, '_group_exists', return_value=True).start()
        self.kill = patch.object(GPU.os, 'killpg').start()
        self.reap = patch.object(self.lifecycle, '_reap_if_child').start()
        self.addCleanup(patch.stopall)

    def test_member_vanishing_after_initial_scan_cannot_authorize_a_signal(self):
        with patch.object(GPU, '_process_details', side_effect=[DETAILS, None]), \
                patch.object(self.lifecycle, '_component_owned', return_value=False), \
                patch.object(GPU.Path, 'read_text', side_effect=FileNotFoundError()), \
                patch.object(GPU, '_group_processes', return_value=[]):
            self.lifecycle._cleanup_state({'lifecycleRoot': ROOT})
            self.kill.assert_not_called()
            self.reap.assert_called_once_with(PID)

    def test_actual_cleanup_waits_for_missing_exe_to_become_zombie_without_signaling(self):
        with patch.object(GPU.Path, 'read_text', side_effect=[kernel_stat(PID, 'R'), kernel_stat(PID, 'S'), kernel_stat(PID, 'Z')]), \
                patch.object(GPU.os, 'readlink', side_effect=FileNotFoundError()), \
                patch.object(GPU.time, 'monotonic', side_effect=[0, 0]), \
                patch.object(GPU.time, 'sleep') as sleep, \
                patch.object(GPU, '_group_processes', return_value=[]):
            self.lifecycle._cleanup_state({'lifecycleRoot': ROOT})
            self.kill.assert_not_called()
            self.reap.assert_called_once_with(PID)
            sleep.assert_called_once_with(0.01)

    def test_unreadable_initial_member_refuses_even_with_another_owned_anchor(self):
        with patch.object(GPU, '_process_details', side_effect=[DETAILS, None]), \
                patch.object(GPU.Path, 'read_text', side_effect=PermissionError()), \
                patch.object(self.lifecycle, '_component_owned') as owned:
            with self.assertRaisesRegex(RuntimeError, 'unreadable recorded process identity'):
                self.lifecycle._cleanup_state({'lifecycleRoot': ROOT, 'mutter': CHILD})
            owned.assert_not_called()
            self.kill.assert_not_called()

    def test_unreadable_fresh_member_refuses_even_with_another_owned_anchor(self):
        with patch.object(GPU, '_process_details', side_effect=[DETAILS, CHILD_DETAILS, None]), \
                patch.object(self.lifecycle, '_component_owned', side_effect=[True, False]), \
                patch.object(GPU.Path, 'read_text', side_effect=OSError(errno.EIO, 'failed')):
            with self.assertRaisesRegex(RuntimeError, 'unreadable identity'):
                self.lifecycle._cleanup_state({'lifecycleRoot': ROOT, 'mutter': CHILD})
            self.kill.assert_not_called()

    def test_confirmed_vanished_child_preserves_actual_owned_group_anchor(self):
        with patch.object(GPU, '_process_details', side_effect=[DETAILS, CHILD_DETAILS, None]), \
                patch.object(self.lifecycle, '_component_owned', side_effect=[True, False]), \
                patch.object(GPU.Path, 'read_text', side_effect=FileNotFoundError()), \
                patch.object(GPU, '_group_processes', side_effect=[[(PID, DETAILS)], [], [], []]):
            self.lifecycle._cleanup_state({'lifecycleRoot': ROOT, 'mutter': CHILD})
            self.kill.assert_called_once_with(PID, signal.SIGTERM)

    def test_live_reused_pid_refuses_without_using_exit_fallback(self):
        reused = ('999', PID, 1, '/foreign/image', ('/foreign/image',))
        with patch.object(GPU, '_process_details', side_effect=[DETAILS, reused]), \
                patch.object(self.lifecycle, '_component_owned', return_value=False), \
                patch.object(GPU.Path, 'read_text') as read:
            with self.assertRaisesRegex(RuntimeError, 'mismatched identity'):
                self.lifecycle._cleanup_state({'lifecycleRoot': ROOT})
            read.assert_not_called()
            self.kill.assert_not_called()

    def test_confirmed_vanished_last_anchor_still_refuses_foreign_group(self):
        with patch.object(GPU, '_process_details', side_effect=[DETAILS, None]), \
                patch.object(self.lifecycle, '_component_owned', return_value=False), \
                patch.object(GPU.Path, 'read_text', side_effect=FileNotFoundError()), \
                patch.object(GPU, '_group_processes', return_value=[(PID + 2, CHILD_DETAILS)]):
            with self.assertRaisesRegex(RuntimeError, 'losing its ownership anchor'):
                self.lifecycle._cleanup_state({'lifecycleRoot': ROOT})
            self.kill.assert_not_called()

    def test_initial_zombie_without_live_members_is_reaped_without_signal(self):
        with patch.object(GPU, '_process_details', return_value=None), \
                patch.object(GPU.Path, 'read_text', return_value=kernel_stat(PID, 'Z')), \
                patch.object(GPU, '_group_processes', return_value=[]):
            self.lifecycle._cleanup_state({'lifecycleRoot': ROOT})
            self.kill.assert_not_called()
            self.reap.assert_called_once_with(PID)

    def test_escalation_still_refuses_new_group_members(self):
        foreign = [(PID + 5, CHILD_DETAILS)]
        with patch.object(GPU, '_process_details', return_value=DETAILS), \
                patch.object(self.lifecycle, '_component_owned', return_value=True), \
                patch.object(GPU, '_group_processes', side_effect=[[(PID, DETAILS)], foreign, foreign]), \
                patch.object(GPU.time, 'monotonic', side_effect=[0, 6]):
            with self.assertRaisesRegex(RuntimeError, 'force a reused GPU process group'):
                self.lifecycle._cleanup_state({'lifecycleRoot': ROOT})
            self.kill.assert_called_once_with(PID, signal.SIGTERM)

if __name__ == '__main__':
    unittest.main()
