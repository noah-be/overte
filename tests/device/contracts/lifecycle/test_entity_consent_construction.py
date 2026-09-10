"""Actual constructor and syntax blocks; explicit engine/value and consent seams."""
from pathlib import Path
import os, shlex, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[4]
class Construction(unittest.TestCase):
    def test_actual_blocks(self):
        source=(ROOT/'libraries/script-engine/src/ScriptManager.cpp').read_text()
        source=source.split('void ScriptManager::entityScriptContentAvailable(',1)[1]
        construction=source.split('    // THE ACTUAL EVALUATION AND CONSTRUCTION\n',1)[1].split('    if (isURL) {',1)[0]
        syntax='    auto program ='+source.split('    auto program =',1)[1].split('    if (isURL) {',1)[0]
        if os.environ.get('OVERTE_CONSENT_CONSTRUCT_AFTER_REVOKE'):
            construction=construction.replace('if (!consentCurrent()) { return; }','')
        fixture=Path(__file__).with_name('entity-consent-construction-test.cpp').read_text().replace('// ACTUAL_CONSTRUCTION',construction).replace('// ACTUAL_SYNTAX',syntax)
        with tempfile.TemporaryDirectory(prefix='consent-construction-') as directory:
            d=Path(directory);cpp=d/'test.cpp';cpp.write_text(fixture)
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
            subprocess.run(['c++','-std=c++17','-fPIC',str(cpp),'-o',str(d/'test'),*flags],check=True,timeout=20)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=5)
if __name__=='__main__':unittest.main()
