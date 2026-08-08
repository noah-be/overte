#!/usr/bin/env python3
"""Device-free source contracts for Pico world-loading failure paths."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "interface/src/Application.h").read_text(encoding="utf-8")


def function_body(signature: str, next_signature: str) -> str:
    start = APPLICATION.index(signature)
    end = APPLICATION.index(next_signature, start)
    return APPLICATION[start:end]


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
