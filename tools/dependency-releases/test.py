#!/usr/bin/env python3
"""Behavioral tests for dependency resolution, drift and retirement boundaries."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check
import retire
import verify


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = check.load((check.ROOT / check.POLICY).read_text())

    def inventory(self):
        releases, tags = [], {}
        for index, item in enumerate(self.policy["bundles"].values()):
            tags[item["tag"]] = item["tag_object"]
            releases.append({"id": index, "tag_name": item["tag"], "draft": False,
                             "prerelease": False, "assets": [
                                 {"name": n, "digest": "sha256:" + d}
                                 for n, d in item["assets"].items()]})
        return releases, tags

    def test_repository_resolves_all_consumers(self):
        self.assertEqual(check.local_check(check.ROOT), self.policy)

    def test_shared_profile_requires_absent_android_consumers_and_safe_registration(self):
        def read(path):
            if path == "tests/platform-profile.json":
                return '{"platform":"shared"}'
            if path.startswith("android/"):
                raise FileNotFoundError(path)
            return "select-platform-ref:\n  run: exit 1\n"
        check.check_sources(read, [])
        with self.assertRaisesRegex(check.PolicyError, "unexpectedly present"):
            check.check_sources(lambda path: "unexpected" if path.startswith("android/") else read(path), [])
        with self.assertRaisesRegex(check.PolicyError, "registration-only"):
            check.check_sources(lambda path: "uses: actions/checkout" if path.endswith(".yml") else read(path), [])

    def test_android_profile_requires_all_resolver_consumers(self):
        def read(path):
            if path == "tests/platform-profile.json":
                return '{"platform":"android"}'
            return "tools/dependency-releases/check.py get " + check.CONSUMERS[path] + " tag"
        check.check_sources(read, [])
        with self.assertRaisesRegex(check.PolicyError, "central resolver"):
            check.check_sources(lambda path: "obsolete downloader" if path.startswith("android/") else read(path), [])

    def test_rejects_wrong_repository_mutable_tag_and_bad_digest(self):
        for field, value in [("tag", "latest"), ("tag_object", "123"),
                             ("assets", {"../outside": "0" * 64})]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.policy)
                data["bundles"]["phone"][field] = value
                with self.assertRaises(check.PolicyError):
                    check.load(json.dumps(data))
        data = copy.deepcopy(self.policy)
        data["repository"] = "overte-org/overte"
        with self.assertRaises(check.PolicyError):
            check.load(json.dumps(data))

    def test_rejects_duplicate_keys(self):
        with self.assertRaises(check.PolicyError):
            check.load('{"schema":1,"schema":1}')

    def test_checksum_output_works_with_sha256sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contents = b"dependency archive fixture\n"
            (root / "archive.tgz").write_bytes(contents)
            sums = check.checksums({"assets": {"archive.tgz": hashlib.sha256(contents).hexdigest()}})
            result = subprocess.run(["sha256sum", "--check"], input=sums, text=True,
                                    cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0)
            (root / "archive.tgz").write_bytes(b"corrupted")
            result = subprocess.run(["sha256sum", "--check"], input=sums, text=True,
                                    cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_hardcoded_consumer_rejected_but_historical_prose_allowed(self):
        read = lambda p: (check.ROOT / p).read_text()
        check.check_sources(read, ["docs/history.md", "tests/fixture.py"])
        with self.assertRaises(check.PolicyError):
            check.check_sources(read, ["android/new-build.sh"])
        with self.assertRaises(check.PolicyError):
            check.check_sources(lambda p: "download old archive", [])

    def test_duplicate_checksum_file_is_rejected(self):
        with self.assertRaises(check.PolicyError):
            check.check_checksum_paths(["android/common/conan/prebuilt/obsolete.sha256"])

    def test_live_scan_pattern_is_compatible_with_git_extended_regex(self):
        result = subprocess.run(["git", "grep", "-l", "-I", "-E", check.TAG_PATTERN,
                                 "HEAD", "--", check.POLICY], cwd=check.ROOT,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(check.POLICY, result.stdout)

    def test_remote_audit_rejects_stale_topic_and_moving_branches(self):
        releases, tags = self.inventory()
        heads = {"main": "a" * 40, "feature/android-phone/test": "b" * 40}
        stale = copy.deepcopy(self.policy)
        stale["bundles"]["phone"]["tag"] = check.FAMILIES["phone"] + "2"

        def git(*args, **kwargs):
            if args[:2] == ("git", "show"):
                sha, path = args[2].split(":", 1)
                if path == check.POLICY:
                    return json.dumps(stale if sha == "b" * 40 else self.policy)
                return (check.ROOT / path).read_text()
            return ""

        with patch.object(check, "remote_heads", return_value=heads), \
                patch.object(check, "api", return_value={"full_name": check.REPOSITORY}), \
                patch.object(check, "run", side_effect=git), \
                patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            with self.assertRaisesRegex(check.PolicyError, "feature/android-phone/test"):
                check.audit(check.ROOT, True)
            stale = self.policy
            refs = [{"ref": "refs/tags/" + tag, "object": {"sha": sha}} for tag, sha in tags.items()]
            with patch.object(check, "pages", side_effect=[releases, refs]), \
                    patch.object(check, "remote_heads", side_effect=[heads, {"main": "c" * 40}]):
                with self.assertRaisesRegex(check.PolicyError, "moved during audit"):
                    check.audit(check.ROOT, True)

    def test_inventory_accepts_only_current_dependencies(self):
        releases, tags = self.inventory()
        # Product releases are a separate lifecycle.
        releases.append({"tag_name": "personal-alpha-1"})
        self.assertEqual(check.inventory(self.policy, releases, tags, False), [])

    def test_inventory_missing_mutated_or_duplicate_current_release_fails(self):
        for change in ("missing", "digest", "tag", "duplicate", "draft"):
            with self.subTest(change=change):
                releases, tags = self.inventory()
                if change == "missing":
                    releases.pop()
                elif change == "digest":
                    releases[0]["assets"][0]["digest"] = None
                elif change == "tag":
                    tags[releases[0]["tag_name"]] = "a" * 40
                elif change == "duplicate":
                    releases.append(releases[0])
                else:
                    releases[0]["draft"] = True
                with self.assertRaises(check.PolicyError):
                    check.inventory(self.policy, releases, tags, False)

    def test_orphan_old_tag_blocks_strict_inventory(self):
        releases, tags = self.inventory()
        old = check.FAMILIES["phone"] + "1"
        tags[old] = "b" * 40
        with self.assertRaises(check.PolicyError):
            check.inventory(self.policy, releases, tags, False)
        self.assertEqual(check.inventory(self.policy, releases, tags, True), [old])

    def test_retirement_never_deletes_newer_or_unrelated_versions(self):
        for tag in [check.FAMILIES["phone"] + "999", "personal-alpha-1",
                    self.policy["bundles"]["phone"]["tag"]]:
            with self.subTest(tag=tag), self.assertRaises(check.PolicyError):
                retire.retirement_candidates({"policy": self.policy,
                                              "retirement_candidates": {tag: "c" * 40}})

    def test_no_mutation_outside_fork(self):
        with patch.object(retire, "api") as request:
            with self.assertRaises(check.PolicyError):
                retire.mutation("repos/overte-org/overte/releases/1", "DELETE", Path("/tmp"))
            request.assert_not_called()

    def test_failed_verification_cannot_delete(self):
        plan = {"policy": self.policy, "retirement_candidates": {check.FAMILIES["phone"] + "1": "c" * 40}}
        with patch.object(retire, "audit", return_value=plan), \
                patch.object(retire, "verify", side_effect=ValueError("checksum mismatch")), \
                patch.object(retire, "mutation") as mutation:
            with self.assertRaises(ValueError):
                retire.retire(check.ROOT, Path("/tmp"), "conan")
            mutation.assert_not_called()

    def test_failed_delete_restores_tag_protection(self):
        old = check.FAMILIES["phone"] + "1"
        plan = {"policy": self.policy, "heads": {"main": "a" * 40},
                "retirement_candidates": {old: "c" * 40}}
        rule = {"id": 42, "source": check.REPOSITORY, "source_type": "Repository",
                "name": "Protection", "target": "tag", "enforcement": "active",
                "conditions": {"ref_name": {"include": ["~ALL"], "exclude": []}},
                "rules": [{"type": "deletion"}], "bypass_actors": []}
        saved = copy.deepcopy(rule)
        operations = []
        release = {"id": 123, "tag_name": old,
                   "url": f"https://api.github.com/repos/{check.REPOSITORY}/releases/123"}

        def api(endpoint):
            return saved if "/rulesets/" in endpoint else release

        def mutate(endpoint, method, directory, body=None):
            operations.append(method)
            if method == "DELETE":
                raise RuntimeError("injected API failure")
            saved.update(copy.deepcopy(body))

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(retire, "audit", return_value=plan), \
                patch.object(retire, "verify"), \
                patch.object(retire, "remote_heads", return_value=plan["heads"]), \
                patch.object(retire, "pages", side_effect=[[release], [rule]]), \
                patch.object(retire, "api", side_effect=api), \
                patch.object(retire, "mutation", side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, "injected API failure"):
                retire.retire(check.ROOT, Path(tmp), "conan")
            self.assertEqual(saved, rule)
            self.assertEqual(operations, ["PUT", "DELETE", "PUT"])

    def test_corrupt_cached_download_is_not_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            bundle = self.policy["bundles"]["phone"]
            destination = directory / bundle["tag"]
            destination.mkdir()
            (destination / next(iter(bundle["assets"]))).write_bytes(b"corrupted")
            with patch.object(verify.subprocess, "run") as execute:
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    verify.verify(check.ROOT, directory, "conan")
                execute.assert_not_called()

    def test_isolated_restores_never_use_owner_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            destination = Path(tmp) / "downloads"
            (root / ".github").mkdir(parents=True)
            policy = copy.deepcopy(self.policy)
            for bundle in policy["bundles"].values():
                for name in bundle["assets"]:
                    contents = name.encode()
                    bundle["assets"][name] = hashlib.sha256(contents).hexdigest()
                    archive = destination / bundle["tag"] / name
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    archive.write_bytes(contents)
            (root / check.POLICY).write_text(json.dumps(policy))
            with patch.object(verify.subprocess, "run") as execute:
                receipt = verify.verify(root, destination, "fixture-conan")
                self.assertEqual(execute.call_count, 3)
                for call in execute.call_args_list:
                    self.assertEqual(call.args[0][:3], ["fixture-conan", "cache", "restore"])
                    self.assertTrue(call.kwargs["env"]["CONAN_HOME"].startswith(str(destination)))
                    self.assertNotEqual(call.kwargs["env"]["CONAN_HOME"], os.environ.get("CONAN_HOME"))
                self.assertEqual(len(receipt["archives"]), 4)


if __name__ == "__main__":
    unittest.main()
