# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import chrome_browser as chrome


class ChromeBrowser(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.executable = Path(self.directory.name) / "chrome"
        self.executable.write_text("owned executable fixture")
        self.executable.chmod(0o700)

    def version(self, value="Google Chrome 154.0.8037.97\n"):
        return patch.object(chrome.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, value, ""))

    def test_explicit_chrome_is_verified_without_any_fallback(self):
        with self.version() as run, patch.object(chrome.shutil, "which") as which:
            self.assertEqual(chrome.chrome_executable({"OVERTE_BROWSER_CHROME_EXECUTABLE": str(self.executable)}), str(self.executable))
        which.assert_not_called()
        self.assertEqual(run.call_args.args[0], [str(self.executable), "--version"])
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_installed_chrome_and_wrapper_symlink_are_supported(self):
        wrapper = Path(self.directory.name) / "google-chrome-stable"
        wrapper.symlink_to(self.executable)
        with self.version(), patch.object(chrome.shutil, "which", return_value=str(wrapper)) as which:
            self.assertEqual(chrome.chrome_executable({}), str(self.executable))
        which.assert_called_once_with("google-chrome-stable")

    def test_missing_chrome_does_not_select_the_system_browser(self):
        with patch.object(chrome.shutil, "which", return_value=None) as which, patch.object(chrome.subprocess, "run") as run:
            with self.assertRaises(RuntimeError): chrome.chrome_executable({})
        self.assertEqual([c.args[0] for c in which.call_args_list], ["google-chrome-stable", "google-chrome"])
        run.assert_not_called()

    def test_invalid_explicit_selection_does_not_fall_back(self):
        for value in ["", "relative/chrome", "\0", str(Path(self.directory.name) / "absent"), self.directory.name]:
            with self.subTest(value=value), patch.object(chrome.shutil, "which") as which, patch.object(chrome.subprocess, "run") as run:
                with self.assertRaises(RuntimeError): chrome.chrome_executable({"OVERTE_BROWSER_CHROME_EXECUTABLE": value})
                which.assert_not_called(); run.assert_not_called()

    def test_other_browser_brand_and_non_version_output_refuse(self):
        for value in ["Chromium 154.0.8037.97\n", "Mozilla Firefox 154.0\n", "Google Chrome error", "Google Chrome 154.0.8037.97\nextra"]:
            with self.subTest(value=value), self.version(value):
                with self.assertRaises(RuntimeError): chrome.chrome_executable({"OVERTE_BROWSER_CHROME_EXECUTABLE": str(self.executable)})

    def test_failed_version_probe_refuses(self):
        for error in [OSError(), subprocess.TimeoutExpired([], 10), subprocess.CalledProcessError(1, [])]:
            with self.subTest(error=type(error)), patch.object(chrome.subprocess, "run", side_effect=error):
                with self.assertRaises(RuntimeError): chrome.chrome_executable({"OVERTE_BROWSER_CHROME_EXECUTABLE": str(self.executable)})

    def test_open_passes_literal_url_and_explicit_chrome_without_a_shell(self):
        url = "http://127.0.0.1:8090/?literal=$()"
        with patch.object(chrome.subprocess, "Popen") as launch:
            chrome.open_chrome(url, {}, str(self.executable))
        self.assertEqual(launch.call_args.args[0], [str(self.executable), "--new-window", url])
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertNotIn("shell", launch.call_args.kwargs)

    def test_refused_browser_prevents_managed_service_start(self):
        import manage
        with patch("sys.argv", ["manage.py", "start", "--gateway", "--open-browser"]), \
             patch.object(manage, "chrome_executable", side_effect=RuntimeError("Chrome unavailable")), \
             patch.object(manage, "start") as start, patch.object(manage, "open_chrome") as launch:
            with self.assertRaises(RuntimeError): manage.main()
        start.assert_not_called(); launch.assert_not_called()

    def test_start_opens_the_verified_chrome_only_after_success(self):
        import manage
        events = []
        with patch("sys.argv", ["manage.py", "start", "--gateway", "--open-browser"]), \
             patch.object(manage, "chrome_executable", side_effect=lambda: events.append("verified") or str(self.executable)), \
             patch.object(manage, "start", side_effect=lambda gateway: events.append("started")), \
             patch.object(manage, "open_chrome", side_effect=lambda url, executable: events.append((url, executable))):
            manage.main()
        self.assertEqual(events, ["verified", "started", ("http://127.0.0.1:8090", str(self.executable))])


if __name__ == "__main__":
    unittest.main()
