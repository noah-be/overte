#!/usr/bin/env python3
"""Pico SH-005 lifecycle/HTTP startup callers, not full Qt product proof."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shlex
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / 'android/vr/pico/apps/picoInterface'


class SharedLifecycleBindingTest(unittest.TestCase):
    def test_account_settings_and_script_diagnostics_use_original_consumers(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<AccountManager>(true);', setup)
        account = (ROOT / 'libraries/networking/src/AccountManager.cpp').read_text()
        self.assertIn('connect(this, &AccountManager::loginComplete, this, &AccountManager::requestAccountSettings);', account)
        self.assertIn('connect(_postSettingsTimer, &QTimer::timeout, this, &AccountManager::postAccountSettings);', account)
        application = (ROOT / 'interface/src/Application.cpp').read_text()
        self.assertIn('connect(scriptManager.get(), &ScriptManager::infoMessage, scriptEngines, &ScriptEngines::onInfoMessage);', application)
        console = (ROOT / 'interface/src/ui/JSConsole.cpp').read_text()
        self.assertIn('connect(_scriptManager.get(), &ScriptManager::infoMessage, this, &JSConsole::handleInfo);', console)
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('void AccountManager::requestAccountSettings(', path.read_text())
            self.assertNotIn('void ScriptManager::scriptInfoMessage(', path.read_text())
        # Source selection only. Actual Qt methods/class and public-vs-internal
        # diagnostic delivery execute in the separate released focused tests.

    def test_direct_token_import_uses_coupled_original_application_and_store(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertLess(setup.index('AccountManager::installProtectedAccountStore('),
                        setup.index('DependencyManager::set<AccountManager>(true);'))
        source = (ROOT / 'interface/src/Application.cpp').read_text()
        method = source.split('void Application::forceLoginWithTokens(', 1)[1].split('\n}', 1)[0]
        self.assertIn('if (DependencyManager::get<AccountManager>()->setAccessTokens(tokens)) {', method)
        self.assertIn('Setting::Handle<bool>(KEEP_ME_LOGGED_IN_SETTING_NAME, true).set(true);', method)
        self.assertIn('bool setAccessTokens(const QString&',
                      (ROOT / 'libraries/networking/src/AccountManager.h').read_text())
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('Application::forceLoginWithTokens(', path.read_text())
        self.assertFalse((APP / 'overrides/Application.cpp').exists())
        # Original three-body Qt fixture tests behavior separately; this pins
        # Pico's real caller/store selection, not native storage durability.

    def test_domain_login_uses_original_generation_owned_account_manager(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<DomainAccountManager>();', setup)
        self.assertIn('connect(domainAccountManager.data(), &DomainAccountManager::authRequired, '
                      'dialogsManager.data(),\n                &DialogsManager::showDomainLoginDialog);', setup)
        login = (ROOT / 'interface/src/ui/LoginDialog.cpp').read_text()
        constructor = login.split('LoginDialog::LoginDialog(', 1)[1].split('\n}', 1)[0]
        before_account_guard = constructor.split(
            '#if !defined(Q_OS_ANDROID) || defined(ANDROID_APP_PHONE_INTERFACE)', 1)[0]
        connection = 'connect(domainAccountManager.data(), &DomainAccountManager::loginRequestFinished,'
        self.assertEqual(constructor.count(connection), 1)
        self.assertIn(connection, before_account_guard)
        self.assertIn('_domainLoginRequest.sameRequest(ticket)', before_account_guard)
        self.assertIn('!context.current()', before_account_guard)
        self.assertIn('Qt::QueuedConnection', before_account_guard)
        self.assertLess(before_account_guard.index('_domainLoginRequest = {};'),
                        before_account_guard.index('emit handleLoginCompleted();'))
        for reason in ('cancelled', 'timeout', 'failed'):
            self.assertIn('emit handleDomainLoginFailed("' + reason + '");', before_account_guard)
        method = login.split('void LoginDialog::loginDomain(', 1)[1].split('\n}', 1)[0]
        self.assertIn('_domainLoginRequest = DependencyManager::get<DomainAccountManager>()'
                      '->requestAccessToken(username, password);', method)
        self.assertLess(setup.index('DependencyManager::set<DomainAccountManager>();'),
                        setup.index('overte::lifecycle::observeQtVisibility('))
        networking = ROOT / 'libraries/networking/src'
        domain = (networking / 'DomainHandler.cpp').read_text()
        self.assertIn('DependencyManager::get<DomainAccountManager>()->setDomainURL(_domainURL);', domain)
        self.assertIn('domainAccountManager->setAuthURL(extraInfoComponents.value(0));', domain)
        self.assertIn('domainAccountManager->setClientID(extraInfoComponents.value(1));', domain)
        node = (networking / 'NodeList.cpp').read_text()
        self.assertIn('connect(domainAccountManager.data(), &DomainAccountManager::newTokens, '
                      'this, &NodeList::sendDomainServerCheckIn);', node)
        self.assertIn('overte::network::RequestScope _accessTokenRequests;',
                      (networking / 'DomainAccountManager.h').read_text())
        self.assertIn('RequestTicket snapshot() const {',
                      (networking / 'RequestCancellation.h').read_text())
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('void DomainAccountManager::requestAccessToken(', path.read_text())
        # Real original all-method/moc test is separate. These source pins do
        # not imply LoginDialog privacy, TLS, global visibility or full auth proof.

    def test_string_factories_retain_original_shared_engine_callers(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<ScriptEngines>', setup)
        engine = ROOT / 'libraries/script-engine'
        self.assertIn('return std::make_shared<ScriptEngineV8>(manager);',
                      (engine / 'src/ScriptEngine.cpp').read_text())
        manager = (engine / 'src/ScriptManager.cpp').read_text()
        self.assertIn('_engine(newScriptEngine(this))', manager)
        require = manager.split('ScriptValue ScriptManager::require(const QString& moduleId) {', 1)[1]
        self.assertIn('return throwModuleError(modulePath, _engine->newValue(error));', require)
        interface = (engine / 'src/ScriptEngine.h').read_text()
        implementation = (engine / 'src/v8/ScriptEngineV8.h').read_text()
        for kind in ('QString&', 'QLatin1String&', 'char*'):
            signature = 'virtual ScriptValue newValue(const ' + kind + ' value)'
            self.assertIn(signature + ' = 0;', interface)
            self.assertIn(signature + ' override;', implementation)
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('ScriptEngineV8::newValue(', path.read_text())
        # Source wiring only. The released test executes all three original
        # bodies with real Qt/V8, but substitutes engine/value ownership storage.

    def test_account_http_session_retains_original_uuid_owner(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('AccountManager::installProtectedAccountStore(overte::pico::protectedAccountStore())', setup)
        self.assertIn('DependencyManager::set<AccountManager>(true);', setup)
        networking = ROOT / 'libraries/networking/src'
        self.assertIn('QUuid _sessionID { QUuid::createUuid() };',
                      (networking / 'AccountManager.h').read_text())
        source = (networking / 'AccountManager.cpp').read_text()
        self.assertIn('_sessionID = QUuid::fromString(QString::fromLatin1(\n'
                      '                    networkReply->rawHeader(METAVERSE_SESSION_ID_HEADER)));', source)
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('void AccountManager::sendRequest(', path.read_text())
        # Original full request/callback test now compiles the actual QUuid
        # declaration. This source pin is not full networking/transport proof.

    def test_qt_signals_reach_original_shared_dispatch(self):
        # This checks actual caller wiring; the released original-body Qt/V8
        # test executes dispatch. It does not prove registration/lifetime safety.
        engine = ROOT / 'libraries/script-engine'
        self.assertIn('target_v8()', (engine / 'CMakeLists.txt').read_text())
        implementation = (engine / 'src/v8/ScriptEngineV8.cpp').read_text()
        self.assertIn('ScriptObjectV8Proxy::newQObject(this, object, ownership, options)', implementation)
        proxy = (engine / 'src/v8/ScriptObjectV8Proxy.cpp').read_text()
        self.assertIn('new ScriptSignalV8Proxy(_engine, qobject, object, defLookup.value().signal)', proxy)
        self.assertIn('QMetaObject::connect(qobject, _meta.methodIndex(), this, _metaCallId)', proxy)
        body = proxy.split('int ScriptSignalV8Proxy::qt_metacall(', 1)[1].split(
            'int ScriptSignalV8Proxy::discoverMetaCallIdx()', 1)[0]
        self.assertLess(body.index('numArgs > Q_METAMETHOD_INVOKE_MAX_ARGS'),
                        body.index('arguments[arg + 1]'))
        self.assertIn('callbackValue.IsEmpty() || !callbackValue->IsFunction()', body)
        self.assertIn('tryCatch.HasTerminated() || isolate->IsExecutionTerminating()', body)
        self.assertNotIn('popContext()', body)
        self.assertNotIn('ToDetailString(', body)
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('ScriptSignalV8Proxy::qt_metacall(', path.read_text())

    def test_entity_script_callers_use_denied_immutable_client_contexts(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<ScriptEngines>(ScriptManager::CLIENT_SCRIPT,', setup)
        renderer = (ROOT / 'libraries/entities-renderer/src/EntityTreeRenderer.cpp').read_text()
        for owner in ('_persistentEntitiesScriptManager', '_nonPersistentEntitiesScriptManager'):
            self.assertIn(owner + ' = scriptManagerFactory(ScriptManager::ENTITY_CLIENT_SCRIPT,', renderer)
        self.assertIn('scriptEngine->loadEntityScript(entityID, resolveScriptURL(newScriptURL), reload)', renderer)
        manager = ROOT / 'libraries/script-engine/src'
        self.assertIn('const Context _context;', (manager / 'ScriptManager.h').read_text())
        self.assertIn('_context(context)', (manager / 'ScriptManager.cpp').read_text())
        # No native bypass/grant substitute for the missing informed-consent backend.
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('ScriptManager::rejectEntityScriptWithoutConsent(', path.read_text())

    def test_v8_diagnostics_remain_in_original_shared_engine(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<ScriptEngines>', setup)
        engine = ROOT / 'libraries/script-engine'
        self.assertIn('return std::make_shared<ScriptEngineV8>(manager);',
                      (engine / 'src/ScriptEngine.cpp').read_text())
        self.assertIn('target_v8()', (engine / 'CMakeLists.txt').read_text())
        manager = (engine / 'src/ScriptManager.cpp').read_text()
        self.assertIn('_engine(newScriptEngine(this))', manager)
        self.assertIn('_engine->evaluateInClosure(closure,', manager)
        implementation = (engine / 'src/v8/ScriptEngineV8.cpp').read_text()
        self.assertIn('if (!storeGlobalObjectContents())', implementation)
        self.assertIn('overte::scripting::copyEnumerableProperties(', implementation)
        for name in ('ScriptEngineV8.cpp', 'ScriptProgramV8Wrapper.cpp'):
            source = (engine / 'src/v8' / name).read_text()
            self.assertIn('#include "V8ExceptionDiagnostics.h"', source)
            self.assertIn('overte::scripting::exceptionDiagnostics(', source)
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('ScriptProgramV8Wrapper::compile()', path.read_text())
            self.assertNotIn('ScriptEngineV8::formatErrorMessageFromTryCatch(', path.read_text())
            self.assertNotIn('ScriptEngineV8::storeGlobalObjectContents()', path.read_text())

    def test_direct_dns_uses_original_networking_owner(self):
        pico = (APP / 'CMakeLists.txt').read_text()
        self.assertIn('shared task networking qml', pico)
        self.assertIn('add_subdirectory("${CMAKE_SOURCE_DIR}/interface"', pico)
        networking = ROOT / 'libraries/networking'
        self.assertIn('setup_hifi_library(Network WebSockets)',
                      (networking / 'CMakeLists.txt').read_text())
        node = (networking / 'src/NodeList.h').read_text()
        self.assertIn('DomainHandler& getDomainHandler() { return _domainHandler; }', node)
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('const DomainHandler& domainHandler = nodeList->getDomainHandler();', setup)
        header = (networking / 'src/DomainHandler.h').read_text()
        self.assertIn('overte::network::ScopedHostnameLookup _hostnameLookup;', header)
        # The original Shared helper/caller is executable-tested by the release.
        # Pico does not fork those methods into its full-copy Setup override.
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('void DomainHandler::setURLAndID(', path.read_text())
            self.assertNotIn('class ScopedHostnameLookup', path.read_text())

    def test_ice_discovery_reaches_original_scoped_lookup(self):
        networking = ROOT / 'libraries/networking/src'
        node = (networking / 'NodeList.cpp').read_text()
        self.assertIn('connect(addressManager.data(), &AddressManager::possibleDomainChangeRequiredViaICEForID,\n'
                      '            &_domainHandler, &DomainHandler::setIceServerHostnameAndID);', node)
        self.assertIn('connect(&_domainHandler, &DomainHandler::iceSocketAndIDReceived, '
                      'this, &NodeList::handleICEConnectionToDomainServer);', node)
        source = (networking / 'DomainHandler.cpp').read_text()
        setter = source.split('void DomainHandler::setIceServerHostnameAndID(', 1)[1].split(
            'void DomainHandler::activateICELocalSocket()', 1)[0]
        self.assertIn('resolveIceHostname();', setter)
        helper = source.split('void DomainHandler::resolveIceHostname()', 1)[1].split(
            'void DomainHandler::hardReset(', 1)[0]
        self.assertIn('_iceHostnameLookup.start(_iceServerHostname, this,', helper)
        self.assertIn('if (!discoveryTicket.current()', helper)
        node_header = (networking / 'NodeList.h').read_text()
        self.assertIn('_domainHandler.setClientDiscoveryVisibility(foreground);', node_header)
        self.assertNotIn('~SockAddr', setter)
        self.assertNotIn('&SockAddr::lookupCompleted', setter)
        reset = source.split('void DomainHandler::hardReset(QString reason) {', 1)[1]
        self.assertLess(reset.index('_iceHostnameLookup.cancel();'), reset.index('emit resetting();'))
        self.assertIn('overte::network::ScopedHostnameLookup _iceHostnameLookup;',
                      (networking / 'DomainHandler.h').read_text())
        # The release runs original setter/completion and cancellation prefix;
        # this source check pins the actual path, not full transport execution.
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('void DomainHandler::setIceServerHostnameAndID(', path.read_text())

    def test_released_http_hook_compiles_in_actual_free_function_scope(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        # setupEssentials is a FREE function, not an Application member.
        body = setup.split('bool setupEssentials(', 1)[1]
        hook = next(line.strip() for line in body.splitlines()
                    if 'observeQtVisibility(' in line)
        source = ('#include <QtGui/QGuiApplication>\n'
                  '#include "interface/src/ApplicationLifecycle.h"\n'
                  '#include "interface/src/PicoQtVisibility.h"\n'
                  'struct AddressManager { void setClientLookupVisibility(bool); };\n'
                  'struct DependencyManager { template<class T> static T* get(); };\n'
                  'void setupEssentials() {\n' + hook + '\n}\n')
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', 'Qt6Gui'], text=True))
        result = subprocess.run(['c++', '-std=c++17', '-fPIC', '-fsyntax-only', '-I', str(ROOT), '-x', 'c++', '-', *flags],
            input=source, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])

    def test_http_visibility_hook_precedes_dependent_startup(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        hook = ('overte::lifecycle::observeQtVisibility'
                '(QGuiApplication::applicationState() == Qt::ApplicationActive);')
        self.assertIn('#include "ApplicationLifecycle.h"', setup)
        self.assertEqual(setup.count(hook), 1)
        after_create = setup.split('DependencyManager::set<AddressManager>();', 1)[1]
        node_creation = 'DependencyManager::set<NodeList>(NodeType::Agent, listenPort);'
        self.assertTrue(after_create.lstrip().startswith(node_creation))
        before_next_dependency = after_create.split(node_creation, 1)[1].split('DependencyManager::set<recording::ClipCache>', 1)[0]
        self.assertIn(hook, before_next_dependency)
        self.assertIn('overte::pico::qtVisible(QGuiApplication::applicationState())', before_next_dependency)
        events = (ROOT / 'interface/src/Application_Events.cpp').read_text()
        body = events.split('void Application::activeChanged(Qt::ApplicationState state) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('observeQtVisibility(state == Qt::ApplicationActive)', body)
        self.assertIn('setClientLookupVisibility(effective)', events)
        self.assertIn('setClientTransportVisibility(effective)', events)
        address_header = (ROOT / 'libraries/networking/src/AddressManager.h').read_text()
        self.assertLess(address_header.index('void setClientLookupVisibility('),
                        address_header.index('public slots:'))
        # Original Shared classes implement cancellation. The Pico hook neither
        # recreates AccountManager/AddressManager nor clones RequestScope.
        for path in APP.rglob('*.cpp'):
            self.assertNotIn('void AddressManager::setClientLookupVisibility(', path.read_text())

    def test_real_pico_override_retains_qt_visibility_connection(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        signals = setup.split('void Application::setupSignalsAndOperators()', 1)[1]
        self.assertIn('connect(this, &Application::applicationStateChanged, this, &Application::activeChanged)', signals)
        connected = signals.split('connect(this, &Application::applicationStateChanged, this, &Application::activeChanged);', 1)[1]
        self.assertIn('activeChanged(applicationState());', connected.split('connect(', 1)[0])
        events = (ROOT / 'interface/src/Application_Events.cpp').read_text()
        body = events.split('void Application::activeChanged(Qt::ApplicationState state) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('observeQtVisibility(state == Qt::ApplicationActive)', body)

    def test_gate_and_events_remain_on_full_interface_target(self):
        cmake = (APP / 'CMakeLists.txt').read_text()
        self.assertIn('add_subdirectory("${CMAKE_SOURCE_DIR}/interface"', cmake)
        self.assertIn('target_link_libraries(${TARGET_NAME} android log m interface)', cmake)
        self.assertNotIn('Application_Events', cmake)
        self.assertNotIn('ApplicationLifecycle', cmake)
        full = (ROOT / 'interface/CMakeLists.txt').read_text()
        self.assertIn('file(GLOB_RECURSE INTERFACE_SRCS "src/*.cpp" "src/*.h")', full)
        source = (ROOT / 'interface/src/Application.cpp').read_text()
        self.assertEqual(source.count('Gate& overte::lifecycle::applicationGate()'), 1)
        # An early-loaded Pico DSO must not silently create a second full-client
        # gate or link interface merely to resolve that singleton.
        for path in APP.rglob('*.cpp'):
            self.assertNotRegex(path.read_text(), r'Gate\s*&\s*(?:overte::lifecycle::)?applicationGate\s*\(', str(path.relative_to(APP)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
