"""Actual complete ScriptCache implementation; Qt delivery and resource seam."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[4]
class ConsentCache(unittest.TestCase):
    def test_actual_cache(self):
        header = (ROOT / 'libraries/script-engine/src/ScriptCache.h').read_text().replace('#include <DependencyManager.h>', '')
        source = (ROOT / 'libraries/script-engine/src/ScriptCache.cpp').read_text()
        source = source[source.index('const QString ScriptCache::STATUS_INLINE'):]
        if os.environ.get('OVERTE_CONSENT_MIX_CACHE_MODES'):
            source = source.replace('cacheKey(url, failOnRedirect, consentScope)', 'cacheKey(url, false, {})')
        if os.environ.get('OVERTE_CONSENT_MIX_SESSIONS'):
            header = header.replace('strict && scope ? scope->identity() : QUuid()', 'QUuid()')
        if os.environ.get('OVERTE_CONSENT_DROP_RESOURCE_POLICY'):
            source = source.replace('request->setFailOnRedirect(failOnRedirect);', '')
        fixture = Path(__file__).with_name('consent-script-cache-test.cpp').read_text()
        fixture = fixture.replace('// ACTUAL_HEADER', header).replace('// ACTUAL_SOURCE', source)
        with tempfile.TemporaryDirectory(prefix='consent-script-cache-') as directory:
            d = Path(directory); cpp = d / 'test.cpp'; cpp.write_text(fixture)
            subprocess.run(['/usr/lib64/qt6/libexec/moc', str(cpp), '-o', str(d/'test.moc')], check=True, timeout=10)
            flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
            subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I'+str(ROOT/'libraries/script-engine/src'),str(cpp),'-o',str(d/'test'),*flags],check=True,timeout=30)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=10)
if __name__ == '__main__': unittest.main()
