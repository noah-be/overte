"""Compile the actual Phone QtEditText and exercise its Android editor contract."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION = ROOT / 'android/phone/apps/phoneInterface/src/main/java/org/qtproject/qt5/android/QtEditText.java'

STUBS = {
    'android/content/Context.java': 'package android.content; public class Context {}',
    'android/text/InputType.java': 'package android.text; public class InputType { public static final int TYPE_CLASS_TEXT=1; }',
    'android/view/KeyEvent.java': 'package android.view; public class KeyEvent {}',
    'android/view/View.java': '''package android.view;
public class View {
 public View(android.content.Context c) {}
 public void setFocusable(boolean b) {}
 public void setFocusableInTouchMode(boolean b) {}
 public android.view.inputmethod.InputConnection onCreateInputConnection(android.view.inputmethod.EditorInfo e) {return null;}
 public boolean onCheckIsTextEditor() {return false;}
 public boolean onKeyDown(int code, KeyEvent e) {return false;}
}''',
    'android/view/inputmethod/InputConnection.java': 'package android.view.inputmethod; public interface InputConnection {}',
    'android/view/inputmethod/EditorInfo.java': '''package android.view.inputmethod;
public class EditorInfo {
 public static final int IME_FLAG_NO_FULLSCREEN=0x2000000, IME_FLAG_NO_EXTRACT_UI=0x10000000;
 public int inputType, imeOptions, initialCapsMode;
}''',
    'org/qtproject/qt5/android/QtActivityDelegate.java': 'package org.qtproject.qt5.android; public class QtActivityDelegate {}',
    'org/qtproject/qt5/android/QtInputConnection.java': '''package org.qtproject.qt5.android;
public class QtInputConnection implements android.view.inputmethod.InputConnection {
 public final QtEditText owner;
 public int restarts;
 public QtInputConnection(QtEditText owner) {this.owner=owner;}
 public void restartImmInput() {restarts++;}
}''',
    'org/qtproject/qt5/android/PhoneImeTest.java': '''package org.qtproject.qt5.android;
import android.view.inputmethod.EditorInfo;
public class PhoneImeTest {
 private static void check(boolean b) {if (!b) throw new AssertionError("Phone editor contract");}
 public static void main(String[] args) {
  QtActivityDelegate delegate=new QtActivityDelegate();
  QtEditText editor=new QtEditText(new android.content.Context(),delegate);
  editor.setImeOptions(6 | 0x1000000);
  editor.setInputType(0x20001);
  editor.setInitialCapsMode(4096);
  EditorInfo info=new EditorInfo();
  QtInputConnection connection=(QtInputConnection)editor.onCreateInputConnection(info);
  check((info.imeOptions & EditorInfo.IME_FLAG_NO_FULLSCREEN)!=0);
  check((info.imeOptions & EditorInfo.IME_FLAG_NO_EXTRACT_UI)!=0);
  check((info.imeOptions & 0x1000000)!=0);
  check((info.imeOptions & 0xff)==6);
  check(info.inputType==0x20001 && info.initialCapsMode==4096);
  check(connection.owner==editor && editor.getActivityDelegate()==delegate);
  check(editor.onCheckIsTextEditor());
  editor.onKeyDown(67,new android.view.KeyEvent());
  check(connection.restarts==1);
  editor.setImeOptions(2);
  EditorInfo next=new EditorInfo();
  check(editor.onCreateInputConnection(next)!=connection);
  check((next.imeOptions & 0xff)==2);
 }
}''',
}

class PhoneIme(unittest.TestCase):
    def test_real_editor_preserves_input_and_disables_fullscreen_extraction(self):
        with tempfile.TemporaryDirectory(prefix='overte-phone-ime-') as scratch:
            root = Path(scratch)
            for name, source in STUBS.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            editor = root / 'org/qtproject/qt5/android/QtEditText.java'
            fixed = PRODUCTION.read_text()
            mutation = fixed.replace('m_imeOptions | EditorInfo.IME_FLAG_NO_FULLSCREEN\n                | EditorInfo.IME_FLAG_NO_EXTRACT_UI', 'm_imeOptions')
            self.assertNotEqual(fixed, mutation)
            for source, should_pass in ((mutation, False), (fixed, True)):
                editor.write_text(source)
                subprocess.run(['javac', '-d', str(root / 'classes'), *map(str, root.rglob('*.java'))],
                               check=True, capture_output=True, timeout=30)
                result = subprocess.run(['java', '-cp', str(root / 'classes'),
                                         'org.qtproject.qt5.android.PhoneImeTest'],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode == 0, should_pass, result.stderr)

if __name__ == '__main__':
    unittest.main()
