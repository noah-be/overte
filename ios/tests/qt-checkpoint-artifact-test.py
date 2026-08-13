#!/usr/bin/env python3
"""Offline contracts for the Qt workflow-artifact checkpoint helper."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import warnings
import zipfile
import datetime as dt


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "ios/ci/qt-checkpoint-artifact.py"
WORKFLOW = (ROOT / ".github/workflows/ios-qt-source.yml").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("qt_checkpoint", TOOL)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def run(*arguments, ok=True):
    result = subprocess.run([sys.executable, str(TOOL), *map(str, arguments)], text=True, capture_output=True)
    if ok and result.returncode:
        raise AssertionError(result.stderr + result.stdout)
    if not ok and result.returncode == 0:
        raise AssertionError("command unexpectedly succeeded")
    return result


def artifact_zip(payload: Path, destination: Path):
    with zipfile.ZipFile(destination, "w") as output:
        output.write(payload / "checkpoint.tar.gz", "checkpoint.tar.gz")
        output.write(payload / "manifest.json", "manifest.json")


with tempfile.TemporaryDirectory(prefix="qt-checkpoint-test-") as temporary_name:
    temporary = Path(temporary_name)
    prefix = temporary / "prefix"
    (prefix / "bin").mkdir(parents=True)
    executable = prefix / "bin/qmake"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    (prefix / ".qt-hidden").write_text("hidden", encoding="utf-8")
    os.symlink("qmake", prefix / "bin/qmake-link")
    payload = temporary / "payload"
    run(
        "create", "--prefix", prefix, "--kind", "host", "--cache-key", "qt-key",
        "--producer-repository-id", "42", "--producer-branch", "apple-ios", "--output-dir", payload,
    )

    workflow_zip = temporary / "artifact.zip"
    artifact_zip(payload, workflow_zip)
    original_download = module.download_latest
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    selected = {"id": 7, "created_at": created_at}
    module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
        destination.write_bytes(workflow_zip.read_bytes()) and selected
    )
    try:
        output = temporary / "github-output"
        install = temporary / "restored"
        args = type("Args", (), dict(
            artifact_prefix="qt-host", kind="host", cache_key="qt-key", install_root=str(install),
            github_output=str(output), expected_repository_id=42, expected_branch="apple-ios", max_age_days=21,
        ))()
        module.restore(args)
        assert "restored=true\n" in output.read_text()
        restored_prefix = install / "macos"
        assert (restored_prefix / ".qt-hidden").read_text() == "hidden"
        stat_mode = (restored_prefix / "bin/qmake").stat().st_mode & 0o777
        assert stat_mode == 0o755
        assert (restored_prefix / "bin/qmake-link").is_symlink()
        assert os.readlink(restored_prefix / "bin/qmake-link") == "qmake"

        for field, value in (("cacheKey", "wrong"), ("kind", "ios")):
            bad = temporary / f"bad-{field}"
            bad.mkdir()
            (bad / "checkpoint.tar.gz").write_bytes((payload / "checkpoint.tar.gz").read_bytes())
            manifest = json.loads((payload / "manifest.json").read_text())
            manifest[field] = value
            (bad / "manifest.json").write_text(json.dumps(manifest))
            try:
                module.validate_manifest(bad, "host", "qt-key")
                raise AssertionError(f"accepted wrong {field}")
            except SystemExit:
                pass

        corrupt = temporary / "corrupt"
        corrupt.mkdir()
        (corrupt / "checkpoint.tar.gz").write_bytes(b"corrupt")
        (corrupt / "manifest.json").write_bytes((payload / "manifest.json").read_bytes())
        try:
            module.validate_manifest(corrupt, "host", "qt-key")
            raise AssertionError("accepted wrong SHA")
        except SystemExit:
            pass

        traversal = temporary / "traversal.tar.gz"
        with tarfile.open(traversal, "w:gz") as archive:
            info = tarfile.TarInfo("../escape")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
        target = temporary / "traversal-target"
        target.mkdir()
        try:
            module.safe_extract(traversal, target)
            raise AssertionError("accepted path traversal")
        except SystemExit:
            pass
        assert not (temporary / "escape").exists()

        missing_output = temporary / "missing-output"
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: None
        missing_args = type("Args", (), dict(
            artifact_prefix="missing", kind="host", cache_key="qt-key", install_root=str(temporary / "unused"),
            github_output=str(missing_output), expected_repository_id=42, expected_branch="apple-ios", max_age_days=21,
        ))()
        module.restore(missing_args)
        assert "restored=false\n" in missing_output.read_text()

        stale_restore_output = temporary / "stale-restore-output"
        stale_install = temporary / "stale-restored"
        stale_selected = {
            "id": 8,
            "created_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=22)).isoformat(),
        }
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
            destination.write_bytes(workflow_zip.read_bytes()) and stale_selected
        )
        stale_args = type("Args", (), dict(
            artifact_prefix="qt-host", kind="host", cache_key="qt-key",
            install_root=str(stale_install), github_output=str(stale_restore_output),
            expected_repository_id=42, expected_branch="apple-ios", max_age_days=21,
        ))()
        module.restore(stale_args)
        assert stale_restore_output.read_text() == "available=true\nfresh=false\nrestored=true\n"
        assert (stale_install / "macos/bin/qmake").is_file()

        v8_payload = temporary / "v8-payload"
        run(
            "create", "--prefix", prefix, "--kind", "v8", "--cache-key", "v8-key",
            "--producer-repository-id", "42", "--producer-branch", "apple-ios",
            "--output-dir", v8_payload,
        )
        v8_zip = temporary / "v8-artifact.zip"
        artifact_zip(v8_payload, v8_zip)
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
            destination.write_bytes(v8_zip.read_bytes()) and selected
        )
        v8_output = temporary / "v8-output"
        v8_install = temporary / "v8-restored"
        v8_args = type("Args", (), dict(
            artifact_prefix="v8", kind="v8", cache_key="v8-key",
            install_root=str(v8_install), github_output=str(v8_output),
            expected_repository_id=42, expected_branch="apple-ios", max_age_days=21,
        ))()
        module.restore(v8_args)
        assert v8_output.read_text() == "available=true\nfresh=true\nrestored=true\n"
        assert (v8_install / "v8-ios/bin/qmake").stat().st_mode & 0o777 == 0o755

        conan_payload = temporary / "conan-payload"
        run(
            "create", "--prefix", prefix, "--kind", "conan", "--cache-key", "conan-key",
            "--producer-repository-id", "42", "--producer-branch", "apple-ios",
            "--output-dir", conan_payload,
        )
        conan_zip = temporary / "conan-artifact.zip"
        artifact_zip(conan_payload, conan_zip)
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
            destination.write_bytes(conan_zip.read_bytes()) and selected
        )
        conan_output = temporary / "conan-output"
        conan_install = temporary / "conan-restored"
        conan_args = type("Args", (), dict(
            artifact_prefix="conan", kind="conan", cache_key="conan-key",
            install_root=str(conan_install), github_output=str(conan_output),
            expected_repository_id=42, expected_branch="apple-ios", max_age_days=21,
        ))()
        module.restore(conan_args)
        assert conan_output.read_text() == "available=true\nfresh=true\nrestored=true\n"
        assert (conan_install / "conan-home/.qt-hidden").read_text() == "hidden"

        for bad_name in ("nested/manifest.json", "extra"):
            invalid_zip = temporary / (bad_name.replace("/", "-") + ".zip")
            with zipfile.ZipFile(invalid_zip, "w") as archive:
                archive.write(payload / "checkpoint.tar.gz", "checkpoint.tar.gz")
                archive.write(payload / "manifest.json", "manifest.json")
                archive.writestr(bad_name, b"x")
            invalid_destination = temporary / (bad_name.replace("/", "-") + "-out")
            invalid_destination.mkdir()
            try:
                module.unpack_payload(invalid_zip, invalid_destination, "host")
                raise AssertionError("accepted nested/extra ZIP member")
            except SystemExit:
                pass

        duplicate_zip = temporary / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate_zip, "w") as archive:
                archive.write(payload / "checkpoint.tar.gz", "checkpoint.tar.gz")
                archive.write(payload / "manifest.json", "manifest.json")
                archive.write(payload / "manifest.json", "manifest.json")
        duplicate_out = temporary / "duplicate-out"
        duplicate_out.mkdir()
        try:
            module.unpack_payload(duplicate_zip, duplicate_out, "host")
            raise AssertionError("accepted duplicate ZIP member")
        except SystemExit:
            pass

        oversized_manifest = temporary / "oversized-manifest"
        oversized_manifest.mkdir()
        (oversized_manifest / "manifest.json").write_bytes(b"x" * (module.MANIFEST_LIMIT + 1))
        (oversized_manifest / "checkpoint.tar.gz").write_bytes(b"x")
        try:
            module.validate_manifest(oversized_manifest, "host", "qt-key")
            raise AssertionError("accepted oversized manifest")
        except SystemExit:
            pass

        expanded = temporary / "expanded.tar.gz"
        with tarfile.open(expanded, "w:gz") as archive:
            info = tarfile.TarInfo("large")
            info.size = 2
            archive.addfile(info, io.BytesIO(b"xx"))
        original_expanded_limit = module.EXPANDED_LIMITS["host"]
        module.EXPANDED_LIMITS["host"] = 1
        try:
            try:
                module.safe_extract(expanded, target)
                raise AssertionError("accepted oversized expanded archive")
            except SystemExit:
                pass
        finally:
            module.EXPANDED_LIMITS["host"] = original_expanded_limit
    finally:
        module.download_latest = original_download

artifacts = [
    {"id": 1, "name": "qt-host-1-1", "created_at": "2026-01-01T00:00:00Z", "expired": False,
     "workflow_run": {"repository_id": 42, "head_repository_id": 42, "head_branch": "apple-ios"}},
    {"id": 2, "name": "qt-host-2-1", "created_at": "2026-02-01T00:00:00Z", "expired": True,
     "workflow_run": {"repository_id": 42, "head_repository_id": 42, "head_branch": "apple-ios"}},
    {"id": 3, "name": "qt-hostile-3-1", "created_at": "2026-03-01T00:00:00Z", "expired": False,
     "workflow_run": {"repository_id": 42, "head_repository_id": 42, "head_branch": "apple-ios"}},
    {"id": 4, "name": "qt-host-4-1", "created_at": "2026-02-01T00:00:00Z", "expired": False,
     "workflow_run": {"repository_id": 42, "head_repository_id": 42, "head_branch": "apple-ios"}},
    {"id": 5, "name": "qt-host-5-1", "created_at": "2026-04-01T00:00:00Z", "expired": False,
     "workflow_run": {"repository_id": 99, "head_repository_id": 99, "head_branch": "apple-ios"}},
    {"id": 6, "name": "qt-host-6-1", "created_at": "2026-05-01T00:00:00Z", "expired": False,
     "workflow_run": {"repository_id": 42, "head_repository_id": 42, "head_branch": "other"}},
]
assert module.select_artifact(artifacts, "qt-host", 42, "apple-ios")["id"] == 4
assert module.select_artifact(artifacts, "qt-host", 99, "apple-ios")["id"] == 5
assert module.select_artifact(artifacts, "qt-host", 42, "other")["id"] == 6
assert module.select_artifact(artifacts, "absent", 42, "apple-ios") is None

for step_name in (
    "Probe validated Qt host artifact fallback",
    "Probe validated Qt iOS artifact fallback",
    "Restore validated Qt host artifact fallback",
    "Restore validated Qt iOS artifact fallback",
):
    start = WORKFLOW.index(f"- name: {step_name}")
    following = WORKFLOW.find("\n      - name:", start + 1)
    step = WORKFLOW[start:following if following >= 0 else len(WORKFLOW)]
    assert "continue-on-error: true" in step, f"optional artifact step can block rebuild: {step_name}"


class FakeResponse:
    def __init__(self, body=b"", headers=None):
        self.body = io.BytesIO(body)
        self.headers = headers or {}
    def read(self, size=-1): return self.body.read(size)
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *unused): self.close()


requests = []
def fake_open(request):
    requests.append(request)
    if len(requests) == 1:
        return FakeResponse(headers={"Location": "https://objects.example/checkpoint"})
    return FakeResponse(b"zip-data")

with tempfile.TemporaryDirectory(prefix="qt-redirect-test-") as redirect_temp:
    downloaded = Path(redirect_temp) / "artifact.zip"
    module.download_artifact(
        "https://api.github.com/artifact", "secret", downloaded,
        module.DOWNLOAD_LIMITS["host"], opener=fake_open,
    )
    assert requests[0].get_header("Authorization") == "Bearer secret"
    assert requests[1].get_header("Authorization") is None
    assert downloaded.read_bytes() == b"zip-data"

fresh = {"created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
stale = {"created_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=22)).isoformat()}
assert module.is_fresh(fresh, 21)
assert not module.is_fresh(stale, 21)

original_find_latest = module.find_latest
try:
    with tempfile.TemporaryDirectory(prefix="qt-probe-test-") as probe_temp:
        probe_output = Path(probe_temp) / "output"
        module.find_latest = lambda prefix, repository_id, branch: (fresh, "token")
        probe_args = type("Args", (), dict(
            artifact_prefix="qt-host", expected_repository_id=42, expected_branch="apple-ios",
            max_age_days=21, github_output=str(probe_output),
        ))()
        module.probe(probe_args)
        assert probe_output.read_text() == "available=true\nfresh=true\n"
        stale_output = Path(probe_temp) / "stale-output"
        module.find_latest = lambda prefix, repository_id, branch: (stale, "token")
        probe_args.github_output = str(stale_output)
        module.probe(probe_args)
        assert stale_output.read_text() == "available=true\nfresh=false\n"
finally:
    module.find_latest = original_find_latest


class TransientUrlOpen:
    def __init__(self):
        self.calls = 0

    def __call__(self, request, timeout):
        assert timeout == 30
        self.calls += 1
        if self.calls < 3:
            raise module.urllib.error.URLError("transient TLS route")
        return FakeResponse(b'{"artifacts": []}')


original_urlopen = module.urllib.request.urlopen
original_sleep = module.time.sleep
try:
    transient = TransientUrlOpen()
    delays = []
    module.urllib.request.urlopen = transient
    module.time.sleep = delays.append
    assert module._github_request("https://api.github.com/test", "token") == b'{"artifacts": []}'
    assert transient.calls == 3
    assert delays == [1, 2]
finally:
    module.urllib.request.urlopen = original_urlopen
    module.time.sleep = original_sleep

try:
    module._read_limited(FakeResponse(b"12345"), 4)
    raise AssertionError("accepted oversized streamed response")
except SystemExit:
    pass
print("Qt checkpoint workflow-artifact tests passed")
