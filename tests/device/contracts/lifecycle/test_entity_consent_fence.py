#!/usr/bin/env python3
"""Actual denial/status functions and entry prefixes, with real Qt dispatch/locks."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class EntityConsentFence(unittest.TestCase):
    def test_actual_deny_paths_and_queued_callbacks(self):
        source = (ROOT / "libraries/script-engine/src/ScriptManager.cpp").read_text()
        header = (ROOT / "libraries/script-engine/src/ScriptManager.h").read_text()
        context = "enum Context {" + header.split("enum Context {", 1)[1].split("};", 1)[0] + "};"
        denial = "bool ScriptManager::bindEntityScriptConsent(" + source.split(
            "bool ScriptManager::bindEntityScriptConsent(", 1)[1].split(
            "void ScriptManager::loadEntityScript(", 1)[0]
        renderer = (ROOT / "libraries/entities-renderer/src/EntityTreeRenderer.cpp").read_text()
        renderer = "void EntityTreeRenderer::endEntityScriptConsent() {" + renderer.split(
            "void EntityTreeRenderer::endEntityScriptConsent() {", 1)[1].split(
            "void EntityTreeRenderer::resetPersistentEntitiesScriptEngine(", 1)[0]
        if os.environ.get("OVERTE_CONSENT_SKIP_RENDERER_SOURCE_CHECK"):
            needle = 'if (!entity || resolveScriptURL(entity->getScript()) != request->source()) { return false; }'
            assert needle in renderer
            renderer = renderer.replace(needle, 'if (!entity) { return false; }')
        environment = "std::function<void(std::function<void()>)> ScriptManager::captureScriptEnvironment() {" + source.split(
            "std::function<void(std::function<void()>)> ScriptManager::captureScriptEnvironment() {", 1)[1].split(
            "void ScriptManager::callWithEnvironment(", 1)[0]
        if os.environ.get("OVERTE_CONSENT_CALLBACK_IGNORE_IDENTITY"):
            environment = environment.replace(
                '_entityScriptConsentRequests.value(entityID).value(consent->source()) == consent', 'true')
        status = "void ScriptManager::updateEntityScriptStatus(" + source.split(
            "void ScriptManager::updateEntityScriptStatus(", 1)[1].split(
            "QVariant ScriptManager::cloneEntityScriptDetails(", 1)[0]
        loader = "void ScriptManager::loadEntityScript(" + source.split(
            "void ScriptManager::loadEntityScript(", 1)[1].split(
            "    PROFILE_RANGE(script, __FUNCTION__);", 1)[0] + "    ++afterLoadFence;\n}\n"
        callback = "void ScriptManager::entityScriptContentAvailable(" + source.split(
            "void ScriptManager::entityScriptContentAvailable(", 1)[1].split(
            "    auto scriptCache = DependencyManager::get<ScriptCache>();", 1)[0] + "    ++afterCallbackFence;\n}\n"
        self.assertIn("const Context _context;", header)
        self.assertIn("rejectEntityScriptWithoutConsent(entityID, entityScript, true, forceRedownload)", loader)
        self.assertIn("rejectEntityScriptWithoutConsent(entityID, scriptOrURL)", callback)
        self.assertNotIn("contents <<", callback)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-consent-fence-") as temporary:
            temporary = pathlib.Path(temporary)
            if os.environ.get("OVERTE_CONSENT_SCOPE_SKIP_STOP"):
                consent = (ROOT / "libraries/script-engine/src/EntityScriptConsent.h").read_text()
                needle = "for (const auto& callback : callbacks) { callback(); }"
                assert needle in consent
                (temporary / "EntityScriptConsent.h").write_text(consent.replace(needle, "// stop-hook negative mutation"))
            (temporary / "context.inc").write_text(context)
            (temporary / "consent-renderer.inc").write_text(renderer)
            (temporary / "consent-fence.inc").write_text(status + denial + loader + callback + environment)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-DTHREAD_DEBUGGING",
                            "-I", str(temporary), "-I", str(ROOT / "libraries/script-engine/src"), str(pathlib.Path(__file__).with_name("entity-consent-fence-test.cpp")),
                            "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
