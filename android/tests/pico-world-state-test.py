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


if __name__ == "__main__":
    unittest.main()
