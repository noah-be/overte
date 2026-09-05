#!/usr/bin/env python3
"""Actual denial/status functions and entry prefixes, with real Qt dispatch/locks."""
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
        denial = "bool ScriptManager::rejectEntityScriptWithoutConsent(" + source.split(
            "bool ScriptManager::rejectEntityScriptWithoutConsent(", 1)[1].split(
            "void ScriptManager::loadEntityScript(", 1)[0]
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
        self.assertIn("rejectEntityScriptWithoutConsent(entityID, entityScript)", loader)
        self.assertIn("rejectEntityScriptWithoutConsent(entityID, scriptOrURL)", callback)
        self.assertNotIn("contents <<", callback)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh005-consent-fence-") as temporary:
            temporary = pathlib.Path(temporary)
            (temporary / "context.inc").write_text(context)
            (temporary / "consent-fence.inc").write_text(status + denial + loader + callback)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-DTHREAD_DEBUGGING",
                            "-I", str(temporary), str(pathlib.Path(__file__).with_name("entity-consent-fence-test.cpp")),
                            "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
