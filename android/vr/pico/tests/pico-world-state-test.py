#!/usr/bin/env python3
"""Device-free source contracts for Pico world-loading failure paths."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "interface/src/Application.h").read_text(encoding="utf-8")
ADDRESS_MANAGER = (ROOT / "libraries/networking/src/AddressManager.cpp").read_text(
    encoding="utf-8")


def function_body(signature: str, next_signature: str) -> str:
    start = APPLICATION.index(signature)
    end = APPLICATION.index(next_signature, start)
    return APPLICATION[start:end]


def without_ios_only_blocks(source: str) -> str:
    """Return the code visible to a non-iOS preprocessor target."""
    visible = []
    skipped_depth = 0
    for line in source.splitlines(keepends=True):
        directive = line.strip()
        if skipped_depth:
            if directive.startswith("#if"):
                skipped_depth += 1
            elif directive.startswith("#endif"):
                skipped_depth -= 1
            continue
        if directive == "#if defined(Q_OS_IOS)":
            skipped_depth = 1
            continue
        visible.append(line)
    if skipped_depth:
        raise AssertionError("unterminated iOS-only preprocessor block")
    return "".join(visible)


class PicoWorldStateTests(unittest.TestCase):
    def test_parser_reports_success_separately_from_named_paths(self):
        self.assertIn("bool prepareServerlessDomainContents", HEADER)
        body = function_body(
            "bool Application::prepareServerlessDomainContents",
            "void Application::loadServerlessDomain",
        )
        parse_failure = body.index("if (!tmpTree->readFromByteArray")
        session_change = body.index("myAvatar->setSessionUUID")
        permission_change = body.index("nodeList->setPermissions")
        entity_send = body.index("tmpTree->sendEntities")
        self.assertLess(parse_failure, session_change)
        self.assertLess(parse_failure, permission_change)
        self.assertLess(parse_failure, entity_send)
        self.assertIn("namedPaths.clear();\n        return false;", body)
        self.assertIn("namedPaths = tmpTree->getNamedPaths();", body)
        self.assertIn("return true;", body)

    def test_local_parse_failure_cannot_commit_or_connect(self):
        body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        failure = body.index("if (!prepareServerlessDomainContents(domainURL, domainData, namedPaths))")
        failure_return = body.index("return;", failure)
        connect = body.index("connectedToServerless(namedPaths)", failure)
        commit = body.index("_picoServerlessSceneImportCommitted = true", failure)
        self.assertLess(failure_return, connect)
        self.assertLess(failure_return, commit)

    def test_explicit_location_is_owned_by_the_single_address_lookup(self):
        body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        pico_visible_body = without_ios_only_blocks(body)
        self.assertNotIn("schedulePicoServerlessLocationQuery", body)
        self.assertNotIn("goToViewpointForPath", pico_visible_body)
        self.assertNotIn("locationApplyFailed", body)

        self.assertIn('const QString LOCATION_QUERY_KEY = "location"', ADDRESS_MANAGER)
        self.assertIn("QUrl::FullyDecoded", ADDRESS_MANAGER)
        self.assertIn(
            "handlePath(path, LookupTrigger::Internal, false)", ADDRESS_MANAGER)

    def test_api_retry_cannot_reapply_a_serverless_spawn(self):
        start = ADDRESS_MANAGER.index("void AddressManager::refreshPreviousLookup()")
        end = ADDRESS_MANAGER.index("void AddressManager::copyAddress()", start)
        body = ADDRESS_MANAGER[start:end]
        self.assertIn("const QUrl address = currentAddress();", body)
        self.assertIn("if (address.scheme() == URL_SCHEME_OVERTE)", body)
        self.assertIn("handleUrl(address, LookupTrigger::AttemptedRefresh);", body)
        self.assertNotIn(
            "handleUrl(currentAddress(), LookupTrigger::AttemptedRefresh);", body)

    def test_startup_fallback_import_preserves_explicit_serverless_url(self):
        fallback = APPLICATION.index("static bool picoStartupImportRequested")
        load = APPLICATION.index("loadServerlessDomain(startupWorld);", fallback)
        body = APPLICATION[fallback:load]
        self.assertIn("const auto explicitStartupScheme = _urlParam.scheme();", body)
        self.assertIn("!_urlParam.isEmpty() && _urlParam.isValid()", body)
        self.assertIn("explicitStartupScheme == HIFI_URL_SCHEME_FILE", body)
        self.assertIn("explicitStartupScheme == HIFI_URL_SCHEME_HTTP", body)
        self.assertIn("explicitStartupScheme == HIFI_URL_SCHEME_HTTPS", body)
        self.assertIn("const QUrl startupWorld = hasExplicitServerlessStartupUrl", body)
        self.assertIn("? _urlParam", body)
        self.assertIn("overte-hub-pico4-optimized-spawn.json", body)
        self.assertLess(body.index("const QUrl startupWorld"), body.index("updateStartupImport"))

    def test_reentrant_serverless_url_does_not_restart_active_import(self):
        load_body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        local_read = load_body.index("PICO_SERVERLESS_TRACE localRead")
        local_prepare = load_body.index(
            "prepareServerlessDomainContents(domainURL, domainData, namedPaths)",
            local_read,
        )
        self.assertLess(
            load_body.index("_picoServerlessSceneImportInProgress = true", local_read),
            local_prepare,
        )

        changed_body = function_body(
            "void Application::domainURLChanged",
            "void Application::domainConnectionRefused",
        )
        guard = changed_body.index("if (_picoServerlessSceneImportInProgress)")
        recursive_load = changed_body.rindex("loadServerlessDomain(domainURL)")
        self.assertLess(guard, recursive_load)
        self.assertIn("normalizedDomainURL == normalizedImportURL", changed_body[guard:recursive_load])
        self.assertIn("return;", changed_body[guard:recursive_load])
        self.assertIn("if (domainURL.isEmpty())", changed_body[guard:recursive_load])
        self.assertIn("if (normalizedDomainURL.isLocalFile())", changed_body[guard:recursive_load])
        self.assertIn(
            "_picoDeferredServerlessSceneURL = domainURL;",
            changed_body[guard:recursive_load],
        )
        finish = load_body.index("const auto finishPicoServerlessImport")
        self.assertIn("Qt::QueuedConnection", load_body[finish:local_read])
        self.assertIn("loadServerlessDomain(deferredURL);", load_body[finish:local_read])
        self.assertEqual(APPLICATION.count('cache/serverless-status'), 3)
        self.assertGreaterEqual(APPLICATION.count("QDateTime::currentMSecsSinceEpoch()"), 3)
        self.assertIn("_picoInitialServerlessHandoffComplete = true;", APPLICATION)
        self.assertIn("if (!_picoInitialServerlessHandoffComplete)", changed_body)

    def test_remote_parse_failure_cannot_commit_or_connect(self):
        body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        failure = body.index("if (!prepareServerlessDomainContents(domainURL, request->getData(), namedPaths))")
        failure_return = body.index("return;", failure)
        connect = body.index("connectedToServerless(namedPaths)", failure)
        commit = body.index("_picoServerlessSceneImportCommitted = true", failure)
        self.assertLess(failure_return, connect)
        self.assertLess(failure_return, commit)

    def test_stale_serverless_request_is_rejected_before_parsing(self):
        body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        generation = body.index("const quint64 requestGeneration = ++_serverlessDomainRequestGeneration")
        send = body.index("request->send();")
        stale_check = body.index("requestGeneration != _serverlessDomainRequestGeneration")
        parse = body.index("prepareServerlessDomainContents(domainURL, request->getData()", stale_check)
        self.assertLess(generation, send)
        self.assertLess(stale_check, parse)
        self.assertIn("staleRequestIgnored", body)

    def test_empty_navigation_invalidates_inflight_serverless_request(self):
        body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        generation = body.index("const quint64 requestGeneration = ++_serverlessDomainRequestGeneration")
        empty = body.index("if (domainURL.isEmpty())")
        empty_return = body.index("return;", empty)
        self.assertLess(generation, empty)
        self.assertLess(empty, empty_return)

    def test_online_navigation_invalidates_serverless_request(self):
        body = function_body(
            "void Application::domainURLChanged",
            "void Application::domainConnectionRefused",
        )
        self.assertIn("if (domainURL.scheme() == URL_SCHEME_OVERTE)", body)
        self.assertIn("++_serverlessDomainRequestGeneration;", body)

    def test_current_serverless_failures_reach_loading_state(self):
        load_body = function_body(
            "void Application::loadServerlessDomain",
            "void Application::loadErrorDomain",
        )
        self.assertIn("_picoServerlessLoadFailed = false;", load_body)
        self.assertGreaterEqual(load_body.count("_picoServerlessLoadFailed = true;"), 4)
        stale_check = load_body.index("requestGeneration != _serverlessDomainRequestGeneration")
        first_async_failure = load_body.index("_picoServerlessLoadFailed = true;", stale_check)
        self.assertGreater(first_async_failure, stale_check)
        self.assertIn(
            "_picoServerlessLoadFailed || _failedToConnectToEntityServer",
            APPLICATION,
        )
        self.assertIn("phase = GraphicsEngine::LoadingPhase::WORLD_SERVER_UNAVAILABLE;", APPLICATION)

    def test_online_navigation_clears_serverless_failure(self):
        body = function_body(
            "void Application::domainURLChanged",
            "void Application::domainConnectionRefused",
        )
        online = body.index("if (domainURL.scheme() == URL_SCHEME_OVERTE)")
        clear = body.index("_picoServerlessLoadFailed = false;", online)
        self.assertGreater(clear, online)


if __name__ == "__main__":
    unittest.main()
