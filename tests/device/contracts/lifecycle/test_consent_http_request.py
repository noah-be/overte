"""Actual HTTP resource methods with Qt request/reply objects; no network."""
import os
from pathlib import Path
import shlex, subprocess, tempfile, unittest
ROOT = Path(__file__).resolve().parents[4]
class ConsentHTTP(unittest.TestCase):
    def test_actual_http_methods(self):
        header=(ROOT/'libraries/networking/src/HTTPResourceRequest.h').read_text().replace('#include "ResourceRequest.h"','')
        source=(ROOT/'libraries/networking/src/HTTPResourceRequest.cpp').read_text()
        source=source[source.index('HTTPResourceRequest::~HTTPResourceRequest()'):]
        if os.environ.get('OVERTE_CONSENT_HTTP_FOLLOW_REDIRECT'):
            source=source.replace('_failOnRedirect ? QNetworkRequest::ManualRedirectPolicy : QNetworkRequest::NoLessSafeRedirectPolicy', 'QNetworkRequest::NoLessSafeRedirectPolicy')
        if os.environ.get('OVERTE_CONSENT_HTTP_ACCEPT_REDIRECT_BODY'):
            source=source.replace('if (_failOnRedirect && (_reply->attribute', 'if (false && (_reply->attribute')
        fixture=Path(__file__).with_name('consent-http-request-test.cpp').read_text().replace('// ACTUAL_HEADER',header).replace('// ACTUAL_SOURCE',source)
        with tempfile.TemporaryDirectory(prefix='consent-http-') as directory:
            d=Path(directory);cpp=d/'test.cpp';cpp.write_text(fixture)
            subprocess.run(['/usr/lib64/qt6/libexec/moc',str(cpp),'-o',str(d/'test.moc')],check=True,timeout=10)
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core','Qt6Network'],text=True))
            subprocess.run(['c++','-std=c++17','-fPIC',str(cpp),'-o',str(d/'test'),*flags],check=True,timeout=30)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],check=True,timeout=10)
if __name__=='__main__': unittest.main()
