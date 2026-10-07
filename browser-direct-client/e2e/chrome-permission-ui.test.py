#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Owned-process/start-tick/input bounds; no real browser, X server or capture."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from Xlib import X

spec = importlib.util.spec_from_file_location("own_chrome_ui", Path(__file__).with_name("chrome-permission-ui.py"))
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class OwnedChromeBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="owned-chrome-ui-regression-")
        self.root = Path(self.directory.name)
        self.profile = self.root / "case" / "profile"
        self.profile.mkdir(parents=True)
        self.browsers = self.root / "browsers"
        self.browsers.mkdir()
        self.executable = self.browsers / "chrome"
        # A real owned sleeper through an executable named chrome exercises
        # /proc identity and parent checks, without launching Chrome or a GUI.
        shutil.copyfile(sys.executable, self.executable); self.executable.chmod(0o700)
        self.process = subprocess.Popen([str(self.executable), "-c", "import time;time.sleep(10)",
                                         f"--user-data-dir={self.profile}"])

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=3)
        self.directory.cleanup()

    def validate(self, record=None, expected=None):
        record = record or ui.process_record(self.process.pid)
        return ui.validate_process(record, self.profile, os.getpid(), self.browsers, expected)

    def test_real_owned_process_ticks_and_parent_are_required(self):
        proof = self.validate()
        self.assertEqual(proof["pid"], self.process.pid)
        self.assertEqual(self.validate(expected=proof), proof)
        with self.assertRaises(RuntimeError):
            self.validate(expected={**proof, "startTicks": str(int(proof["startTicks"]) + 1)})
        record = ui.process_record(self.process.pid)
        with self.assertRaises(RuntimeError):
            ui.validate_process(record,
                                self.profile, os.getpid() + 1000000, self.browsers)
        self.process.terminate(); self.process.wait(timeout=3)
        with self.assertRaises(RuntimeError):
            ui.validate_process(ui.process_record(self.process.pid), self.profile, os.getpid(), self.browsers)

    def test_foreign_profile_download_and_permission_overrides_are_refused(self):
        record = ui.process_record(self.process.pid)
        for argv in ([str(self.browsers / "chrome-real" / "chrome"), "--user-data-dir=/foreign/profile"],
                     ["/foreign/chrome", f"--user-data-dir={self.profile}"],
                     *[[str(self.browsers / "chrome-real" / "chrome"), f"--user-data-dir={self.profile}", flag]
                       for flag in ui.FORBIDDEN_FLAGS]):
            with self.assertRaises(RuntimeError):
                ui.validate_process({**record, "argv": argv}, self.profile, os.getpid(), self.browsers)

    def test_click_never_leaves_the_bound_window_and_binding_is_private_regular(self):
        ui.validate_coordinates(40, 50, {"width": 1280, "height": 800})
        for coordinates in ((-1, 0), (1280, 0), (0, 800), (1.5, 1), (True, 1)):
            with self.assertRaises(RuntimeError):
                ui.validate_coordinates(*coordinates, {"width": 1280, "height": 800})
        path = self.root / "binding.json"
        path.write_text(json.dumps({"window": "fixture"})); path.chmod(0o600)
        self.assertEqual(ui.bounded_json(path), {"window": "fixture"})
        path.chmod(0o644)
        with self.assertRaises(RuntimeError):
            ui.bounded_json(path)
        path.unlink(); os.mkfifo(path, 0o600)
        with self.assertRaises(RuntimeError):
            ui.bounded_json(path)
        path.unlink(); path.symlink_to(self.profile)
        with self.assertRaises(OSError):
            ui.bounded_json(path)

    def test_any_foreign_display_is_refused_before_gui_access(self):
        for display_name in (":0", ":105", ":104.0", "localhost:104"):
            with self.assertRaises(RuntimeError):
                ui.require_private_environment(self.profile, display_name)

    def test_joined_chrome_process_title_restores_exact_arguments_without_weakening_guards(self):
        record = ui.process_record(self.process.pid)
        joined = shlex.join(record["argv"])
        restored = ui.normalise_argv([joined], self.executable)
        self.assertEqual(restored, record["argv"])
        self.assertEqual(ui.validate_process({**record, "argv": restored}, self.profile, os.getpid(), self.browsers)["pid"], self.process.pid)
        for suffix in (" --use-fake-ui-for-media-stream", " --type=renderer", f" --user-data-dir={self.profile}"):
            with self.assertRaises(RuntimeError):
                ui.validate_process({**record, "argv": ui.normalise_argv([joined + suffix], self.executable)},
                                    self.profile, os.getpid(), self.browsers)


class NativeUTF8Window:
    def __init__(self, window_id=20, pid=30, title=ui.TITLE, *, state=X.IsViewable, x=0, y=0,
                 property_type=3, fmt=8, remainder=0, transient=None):
        self.id=window_id; self.pid=pid; self.title=title.encode('utf-8') if isinstance(title,str) else title
        self.state=state; self.x=x; self.y=y; self.property_type=property_type; self.fmt=fmt
        self.remainder=remainder; self.transient=transient; self.requests=[]
    def get_wm_name(self):
        return None  # Native UTF8_STRING does not match Python-Xlib's STRING request.
    def get_property(self, name, req_type, offset, length):
        self.requests.append((name,req_type,offset,length))
        return SimpleNamespace(property_type=self.property_type,format=self.fmt,bytes_after=self.remainder,value=self.title)
    def get_full_property(self, name, req_type):
        return SimpleNamespace(value=[self.pid])
    def get_attributes(self):
        return SimpleNamespace(map_state=self.state,win_class=X.InputOutput)
    def get_geometry(self):
        return SimpleNamespace(width=1280,height=800)
    def get_wm_transient_for(self):
        return self.transient


class NativeUTF8Display:
    def __init__(self, windows):
        self.windows=windows
    def intern_atom(self, name):
        return {'_NET_WM_PID':1,'_NET_WM_NAME':2,'UTF8_STRING':3}[name]
    def screen(self):
        return SimpleNamespace(root=self)
    def query_tree(self):
        return SimpleNamespace(children=self.windows)
    def translate_coords(self, window, x, y):
        return SimpleNamespace(x=window.x,y=window.y)
    def get_geometry(self):
        return SimpleNamespace(width=1280,height=800)


class NativeUTF8OwnedWindowTests(unittest.TestCase):
    def test_actual_native_utf8_title_contract_accepts_one_owned_viewable_window(self):
        window=NativeUTF8Window(title=ui.TITLE+' — Google Chrome for Testing')
        root,owned,bounds,counts=ui.owned_window(NativeUTF8Display([window]),{'pid':30})
        self.assertIs(owned,window)
        self.assertEqual(bounds,{'x':0,'y':0,'width':1280,'height':800})
        self.assertEqual(window.requests,[(2,3,0,129)])
        self.assertEqual(counts['viewableExpectedTitleWindows'],1)

    def test_wrong_type_format_remainder_invalid_utf8_nul_and_oversize_are_refused(self):
        for values in ({'property_type':9},{'fmt':16},{'remainder':1},{'title':b'\xff'},
                       {'title':ui.TITLE+'\0hidden'},{'title':ui.TITLE+'x'*512}):
            with self.subTest(values=list(values)):
                window=NativeUTF8Window(**values)
                with self.assertRaises(RuntimeError):
                    ui.owned_window(NativeUTF8Display([window]),{'pid':30})
                self.assertEqual(window.requests,[(2,3,0,129)])

    def test_wrong_pid_title_unmapped_multiple_and_changed_window_are_refused(self):
        for windows in ([NativeUTF8Window(pid=31)],[NativeUTF8Window(title='Foreign page')],
                        [NativeUTF8Window(state=X.IsUnmapped)],[NativeUTF8Window(),NativeUTF8Window(window_id=21)]):
            with self.assertRaises(RuntimeError):
                ui.owned_window(NativeUTF8Display(windows),{'pid':30})
        with self.assertRaises(RuntimeError):
            ui.owned_window(NativeUTF8Display([NativeUTF8Window()]),{'pid':30},
                            {'windowID':21,'bounds':{'x':0,'y':0,'width':1280,'height':800}})

    def test_foreign_overlapping_window_refuses_capture_but_owned_popup_preserves_binding(self):
        main=NativeUTF8Window()
        with self.assertRaises(RuntimeError):
            ui.owned_window(NativeUTF8Display([main,NativeUTF8Window(window_id=21,pid=31,title='Foreign')]),{'pid':30})
        _,owned,_,_=ui.owned_window(NativeUTF8Display([main,NativeUTF8Window(window_id=21,pid=30,title='Popup')]),{'pid':30})
        self.assertIs(owned,main)

    def test_actual_root_bounds_refuse_oversized_or_clipped_windows_before_capture(self):
        screen={'width':1024,'height':768}
        ui.validate_screen_bounds({'x':0,'y':0,'width':900,'height':686},screen)
        ui.validate_screen_bounds({'x':124,'y':82,'width':900,'height':686},screen)
        for bounds in ({'x':0,'y':0,'width':1280,'height':887},
                       {'x':-1,'y':0,'width':900,'height':686},
                       {'x':0,'y':-1,'width':900,'height':686},
                       {'x':125,'y':0,'width':900,'height':686},
                       {'x':0,'y':83,'width':900,'height':686}):
            with self.subTest(bounds=bounds):
                with self.assertRaises(RuntimeError):
                    ui.validate_screen_bounds(bounds,screen)
        # Exercise the actual owned-window path, not only the arithmetic helper.
        dpy=NativeUTF8Display([NativeUTF8Window()])
        dpy.get_geometry=lambda:SimpleNamespace(width=1024,height=768)
        with self.assertRaisesRegex(RuntimeError,'fit wholly inside'):
            ui.owned_window(dpy,{'pid':30})


if __name__ == "__main__":
    unittest.main()
