#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Actual CLI branch selection; never builds or launches Qt or a display."""
import ast,subprocess,sys,types,unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[2]
BUILDER=SOURCE/'tools/build-native-input.py'
parsed=ast.parse(BUILDER.read_text())
main=next(n for n in parsed.body if isinstance(n,ast.If) and ast.unparse(n.test)=="__name__ == '__main__'")
selection=next(n for n in main.body if isinstance(n,ast.If) and ast.unparse(n.test)=='options.test_web_editors')
class Selection(unittest.TestCase):
 def test_missing_test_flag_is_refused_before_build(self):
  result=subprocess.run([sys.executable,str(BUILDER),'--test-web-editors'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
  self.assertEqual(result.returncode,2);self.assertIn(b'--test-web-editors requires --test',result.stderr)
 def command(self,enabled,node):
  calls=[];scope={'options':types.SimpleNamespace(test_web_editors=enabled),'output':Path('/owned/output'),'runtime':Path('/owned/lab/appimage/squashfs-root/usr/lib'),'SOURCE':SOURCE/'native-input','xvfb':Path('/owned/Xvfb'),'sys':sys,'subprocess':types.SimpleNamespace(run=lambda *args,**kwargs:calls.append((args,kwargs)))}
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(BUILDER),'exec'),scope);return calls
 def test_actual_explicit_branch_preserves_default_system_path(self):
  self.assertEqual(self.command(False,selection),[])
  calls=self.command(True,selection);self.assertEqual(len(calls),1);args,kw=calls[0];command=args[0]
  self.assertEqual(command[:2],[sys.executable,str(SOURCE/'native-input/web-editor/run.py')]);self.assertEqual(command[command.index('--qt-libraries')+1],'/owned/lab/appimage/squashfs-root/usr/lib');self.assertEqual(command[command.index('--qt-test-libraries')+1],'/owned/lab/qt-tablet/usr/lib/x86_64-linux-gnu');self.assertEqual(kw,{'check':True,'timeout':150})
  # The original unconditional followup would wrongly run against system Qt.
  broken=ast.If(test=ast.Constant(value=True),body=selection.body,orelse=[]);ast.fix_missing_locations(broken);self.assertEqual(len(self.command(False,broken)),1)
 def test_only_existing_pinned_actual_qt_input_gate_selects_full_editor_proof(self):
  source=(SOURCE/'ci/jenkins/gates.py').read_text();tree=ast.parse(source)
  stages=[n for n in ast.walk(tree)if isinstance(n,ast.Tuple)and n.elts and isinstance(n.elts[0],ast.Constant)and n.elts[0].value=='actual-qt-input']
  self.assertEqual(len(stages),1);command=ast.unparse(stages[0]);self.assertIn("'--test-web-editors'",command);self.assertIn("'appimage/squashfs-root/usr/lib'",command)
if __name__=='__main__':unittest.main()
