#!/usr/bin/env python3
"""Offline contracts for the Qt workflow-artifact checkpoint helper."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import warnings
from unittest import mock
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

        compiler_payload = temporary / "compiler-payload"
        run("create", "--prefix", prefix, "--kind", "client-sccache", "--cache-key", "compiler-key",
            "--producer-repository-id", "42", "--producer-branch", "apple-ios", "--output-dir", compiler_payload)
        compiler_zip = temporary / "compiler.zip"
        artifact_zip(compiler_payload, compiler_zip)
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
            destination.write_bytes(compiler_zip.read_bytes()) and selected)
        compiler_args = type("Args", (), dict(
            artifact_prefix="compiler", kind="client-sccache", cache_key="compiler-key",
            install_root=str(temporary / "compiler-restored"), github_output=str(temporary / "compiler-output"),
            expected_repository_id=42, expected_branch="apple-ios", max_age_days=21))()
        module.restore(compiler_args)
        assert (temporary / "compiler-restored/client-sccache/.qt-hidden").read_text() == "hidden"
        # The new object kind must retain the exact same provenance/key gates.
        for field, value in (("expected_repository_id", 43), ("expected_branch", "other"), ("cache_key", "other")):
            bad_args = type("Args", (), {})()
            for key in ("artifact_prefix", "kind", "cache_key", "install_root", "github_output",
                        "expected_repository_id", "expected_branch", "max_age_days"):
                setattr(bad_args, key, getattr(compiler_args, key))
            setattr(bad_args, field, value)
            bad_args.install_root = str(temporary / ("bad-compiler-" + field))
            try:
                module.restore(bad_args)
                raise AssertionError("compiler checkpoint accepted mismatching " + field)
            except SystemExit:
                pass

        qt_compiler_payload = temporary / "qt-compiler-payload"
        run("create", "--prefix", prefix, "--kind", "qt-sccache", "--cache-key", "compiler-key",
            "--producer-repository-id", "42", "--producer-branch", "apple-ios", "--output-dir", qt_compiler_payload)
        qt_compiler_zip = temporary / "qt-compiler.zip"
        artifact_zip(qt_compiler_payload, qt_compiler_zip)
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
            destination.write_bytes(qt_compiler_zip.read_bytes()) and selected)
        qt_compiler_args = type("Args", (), dict(
            artifact_prefix="compiler", kind="qt-sccache", cache_key="compiler-key",
            install_root=str(temporary / "qt-compiler-restored"), github_output=str(temporary / "qt-compiler-output"),
            expected_repository_id=42, expected_branch="apple-ios", max_age_days=21))()
        module.restore(qt_compiler_args)
        assert (temporary / "qt-compiler-restored/qt-sccache/.qt-hidden").read_text() == "hidden"
        # The new object kind must retain the exact same provenance/key gates.
        for field, value in (("expected_repository_id", 43), ("expected_branch", "other"), ("cache_key", "other")):
            bad_args = type("Args", (), {})()
            for key in ("artifact_prefix", "kind", "cache_key", "install_root", "github_output",
                        "expected_repository_id", "expected_branch", "max_age_days"):
                setattr(bad_args, key, getattr(qt_compiler_args, key))
            setattr(bad_args, field, value)
            bad_args.install_root = str(temporary / ("bad-qt-compiler-" + field))
            try:
                module.restore(bad_args)
                raise AssertionError("compiler checkpoint accepted mismatching " + field)
            except SystemExit:
                pass

        source_prefix = temporary / "source-downloads"
        source_prefix.mkdir()
        source_name = "qt-everywhere-src-6.11.1.tar.xz"
        source_bytes = lzma.compress(b"pinned Qt source archive fixture")
        (source_prefix / source_name).write_bytes(source_bytes)
        source_payload = temporary / "source-payload"
        run("create", "--prefix", source_prefix, "--kind", "qt-source", "--cache-key", "source-sha-key",
            "--producer-repository-id", "42", "--producer-branch", "apple-ios", "--output-dir", source_payload)
        source_zip = temporary / "source.zip"
        artifact_zip(source_payload, source_zip)
        source_install = temporary / "qt-work"
        module.download_latest = lambda artifact_prefix, repository_id, branch, destination, kind: (
            destination.write_bytes(source_zip.read_bytes()) and selected)
        source_args = type("Args", (), dict(
            artifact_prefix="source", kind="qt-source", cache_key="source-sha-key",
            install_root=str(source_install), github_output=str(temporary / "source-output"),
            expected_repository_id=42, expected_branch="apple-ios", max_age_days=21))()
        module.restore(source_args)
        restored_source = source_install / "downloads" / source_name
        assert restored_source.read_bytes() == source_bytes
        assert module.sha256(restored_source) == module.sha256(source_prefix / source_name)
        assert list((source_install / "downloads").iterdir()) == [restored_source]
        source_manifest = json.loads((source_payload / "manifest.json").read_text())
        assert source_manifest["kind"] == "qt-source"
        assert source_manifest["cacheKey"] == "source-sha-key"
        assert source_manifest["sha256"] == module.sha256(source_payload / "checkpoint.tar.gz")
        # Retain the checkpoint digest gate before the existing source consumer
        # independently verifies the pinned upstream XZ SHA-256.
        with (source_payload / "checkpoint.tar.gz").open("ab") as damaged:
            damaged.write(b"corrupt")
        try:
            module.validate_manifest(source_payload, "qt-source", "source-sha-key")
            raise AssertionError("Qt source checkpoint accepted corrupt payload")
        except SystemExit:
            pass

        # The Qt object kind retains extraction safety and its own size limit.
        qt_unsafe_target = temporary / "qt-unsafe"
        qt_unsafe_target.mkdir()
        try:
            module.safe_extract(traversal, qt_unsafe_target, "qt-sccache")
            raise AssertionError("Qt compiler checkpoint accepted path traversal")
        except SystemExit:
            pass
        qt_limit = module.EXPANDED_LIMITS["qt-sccache"]
        module.EXPANDED_LIMITS["qt-sccache"] = 1
        try:
            try:
                module.safe_extract(qt_compiler_payload / "checkpoint.tar.gz", qt_unsafe_target, "qt-sccache")
                raise AssertionError("Qt compiler checkpoint ignored expanded-size limit")
            except SystemExit:
                pass
        finally:
            module.EXPANDED_LIMITS["qt-sccache"] = qt_limit

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

# The opt-in index reuses only complete, recent repository listings. Selection
# still runs for each request, including every repository/branch provenance gate.
with tempfile.TemporaryDirectory(prefix="artifact-index-test-") as index_temp:
    index = Path(index_temp) / "index.json"
    env = {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "noah-be/overte",
           "OVERTE_ARTIFACT_INDEX_CACHE": str(index)}
    with mock.patch.dict(os.environ, env), mock.patch.object(module.time, "time", return_value=1000):
        response = json.dumps({"artifacts": artifacts}).encode()
        with mock.patch.object(module, "_github_request", return_value=response) as api:
            assert module.find_latest("qt-host", 42, "apple-ios")[0]["id"] == 4
            assert module.find_latest("qt-host", 42, "other")[0]["id"] == 6
            assert module.find_latest("qt-host", 99, "apple-ios")[0]["id"] == 5
            assert module.find_latest("missing", 42, "apple-ios")[0] is None
            assert api.call_count == 1
        good = json.loads(index.read_text())
        for bad in (
            {**good, "fetchedAt": 879}, {**good, "fetchedAt": 1001},
            {**good, "repository": "another/repository"}, {**good, "schema": 99},
            {**good, "artifacts": [None]}, {**good, "artifacts": [{"name": 42}]},
            {**good, "artifacts": [{"name": "qt-host-1", "workflow_run": None}]},
            {**good, "artifacts": [{**artifacts[0], "id": "not-an-id"}]},
            {**good, "artifacts": [{**artifacts[0], "created_at": []}]},
            {**good, "artifacts": [{**artifacts[0], "expired": "false"}]},
            [], "invalid JSON",
        ):
            index.write_text(bad if isinstance(bad, str) else json.dumps(bad))
            with mock.patch.object(module, "_github_request", return_value=response) as api:
                assert module.find_latest("qt-host", 42, "apple-ios")[0]["id"] == 4
                assert api.call_count == 1
                assert json.loads(index.read_text()) == good

        # No configured path means no cache and preserves fresh-list behavior.
        with mock.patch.dict(os.environ, {"OVERTE_ARTIFACT_INDEX_CACHE": ""}), \
             mock.patch.object(module, "_github_request", return_value=response) as api:
            module.find_latest("qt-host", 42, "apple-ios")
            module.find_latest("qt-host", 42, "apple-ios")
            assert api.call_count == 2

        # Failed second-page fetch must not overwrite even an expired index.
        expired = json.dumps({**good, "fetchedAt": 1})
        index.write_text(expired)
        page = json.dumps({"artifacts": [artifacts[0]] * 100}).encode()
        error = module.urllib.error.HTTPError("https://api.github.com/test", 503, "unavailable", {}, None)
        with mock.patch.object(module, "_github_request", side_effect=[page, error]) as api:
            try:
                module.find_latest("qt-host", 42, "apple-ios")
                raise AssertionError("API failure was ignored")
            except module.urllib.error.HTTPError:
                pass
            assert api.call_count == 2
            assert index.read_text() == expired
        with mock.patch.object(module, "_github_request", side_effect=[page, response]) as api:
            assert module.find_latest("qt-host", 42, "apple-ios")[0]["id"] == 4
            assert api.call_count == 2
            assert len(json.loads(index.read_text())["artifacts"]) == 106

        # Preserve the existing 100-page bound but never cache a truncated index.
        index.write_text(expired)
        with mock.patch.object(module, "_github_request", return_value=page) as api:
            assert module.find_latest("qt-host", 42, "apple-ios")[0]["id"] == 1
            assert api.call_count == 100
            assert index.read_text() == expired

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
