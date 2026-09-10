"""Actual Application consent methods with Qt dispatch and explicit UI seams."""
from pathlib import Path
import os,shlex,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class ApplicationConsent(unittest.TestCase):
    def test_actual_application_consent(self):
        source=(ROOT/'interface/src/Application_UI.cpp').read_text()
        source='void Application::invalidateEntityScriptConsent() {'+source.split('void Application::invalidateEntityScriptConsent() {',1)[1].split('bool Application::askToLoadScript(',1)[0]
        domain=(ROOT/'interface/src/Application.cpp').read_text()
        source += 'void Application::domainURLChanged(QUrl domainURL) {'+domain.split('void Application::domainURLChanged(QUrl domainURL) {',1)[1].split('void Application::domainConnectionRefused(',1)[0]
        entities=(ROOT/'interface/src/Application_Entities.cpp').read_text()
        source += 'void Application::resettingDomain() {'+entities.split('void Application::resettingDomain() {',1)[1].split('void Application::queryOctree(',1)[0]
        if os.environ.get('OVERTE_CONSENT_REVOKE_REDUNDANT_DOMAIN'):
            source=source.replace('void Application::domainURLChanged(QUrl domainURL) {','void Application::domainURLChanged(QUrl domainURL) { invalidateEntityScriptConsent();')
        if os.environ.get('OVERTE_CONSENT_UI_SKIP_SESSION_CHECK'):

            source=source.replace('request->active() && request->belongsTo(_entityScriptConsentScope) &&','true &&')
        fixture=Path(__file__).with_name('entity-consent-application-test.cpp').read_text().replace('// ACTUAL_SOURCE',source)
        with tempfile.TemporaryDirectory(prefix='consent-application-') as directory:
            d=Path(directory);cpp=d/'test.cpp';cpp.write_text(fixture)
            subprocess.run(['/usr/lib64/qt6/libexec/moc',str(cpp),'-o',str(d/'test.moc')],check=True,timeout=10)
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Widgets'],text=True))
            subprocess.run(['c++','-DANDROID_APP_PICO_INTERFACE','-std=c++17','-fPIC','-pthread','-I',str(ROOT/'libraries/script-engine/src'),str(cpp),'-o',str(d/'test'),*flags],check=True,timeout=30)
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software')
            subprocess.run(['unshare','--user','--map-root-user','--net',str(d/'test')],env=env,check=True,timeout=10)
if __name__=='__main__':unittest.main()
