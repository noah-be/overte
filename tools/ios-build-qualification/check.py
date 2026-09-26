#!/usr/bin/env python3
"""Trusted iOS merge-candidate routing and physical-device artifact verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "noah-be/overte"
REPOSITORY_ID = 1319052603
CONTEXT = "ios-device-build"
JOBS = {"route", "host", "qt", "client"}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True,
                                   stderr=subprocess.PIPE, timeout=30).strip()


def validate_wiring(candidate, event, policy_root=ROOT):
    """Called by the independently required, default-branch repository router.

    This prevents a PR from making the final build check optional/skipped or
    replacing its verifier. The flag is staged off until the workflow is deployed.
    """
    if event.get("pull_request", {}).get("base", {}).get("ref") != "apple-ios":
        return
    config = json.loads((policy_root / ".github/ios-build-qualification.json").read_text())
    require(config.get("schema") == 1 and config.get("repository") == REPOSITORY
            and config.get("repositoryId") == REPOSITORY_ID
            and config.get("requiredContext") == CONTEXT
            and type(config.get("enforceWorkflow")) is bool
            and config.get("workflowPath") == ".github/workflows/ios-build-qualification.yml",
            "invalid trusted build qualification policy")
    path = candidate / config["workflowPath"]
    if not path.exists() and not config["enforceWorkflow"]:
        return
    require(path.is_file() and not path.is_symlink(), "required iOS qualification workflow missing")
    canonical = (policy_root / "tools/ios-build-qualification/workflow.yml").read_text()
    require(path.read_text() == canonical,
            "iOS build workflow differs from trusted orchestration; update the parent policy first")


def route(event, candidate, expected_sha):
    repo = event["repository"]
    require(repo["full_name"] == REPOSITORY and repo["id"] == REPOSITORY_ID,
            "foreign repository")
    require(SHA.fullmatch(expected_sha), "invalid candidate revision")
    require(git(candidate, "rev-parse", "HEAD") == expected_sha, "wrong candidate checkout")
    pr = event.get("pull_request")
    if pr:
        require(pr["base"]["ref"] == "apple-ios", "qualification target must be apple-ios")
        for side in ("base", "head"):
            require(pr[side]["repo"]["full_name"] == REPOSITORY
                    and pr[side]["repo"]["id"] == REPOSITORY_ID, "foreign PR source")
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        require(SHA.fullmatch(base) and SHA.fullmatch(head), "invalid PR revisions")
        require(git(candidate, "show", "-s", "--format=%P", expected_sha).split() == [base, head],
                "candidate must merge the exact event base and head")
        # No path allowlist can miss a newly introduced source/build dependency.
        # Only ordinary Markdown changes qualify for the explicit lighter route.
        fields = subprocess.check_output(
            ["git", "diff", "--raw", "--no-renames", "-z", base, expected_sha, "--"],
            cwd=candidate, timeout=30).decode().rstrip("\0").split("\0")
        docs = bool(fields and fields != [""])
        require(fields == [""] or len(fields) % 2 == 0, "incomplete change inventory")
        if fields != [""]:
            for index in range(0, len(fields), 2):
                metadata = fields[index].split()
                require(len(metadata) == 5 and metadata[0].startswith(":"), "invalid change metadata")
                path = PurePosixPath(fields[index + 1])
                require(not path.is_absolute() and ".." not in path.parts, "invalid changed path")
                docs &= path.suffix == ".md" and all(
                    mode in {"000000", "100644"} for mode in (metadata[0][1:], metadata[1]))
    else:
        docs, base, head = False, "", expected_sha
    return {"required": "false" if docs else "true", "source": expected_sha,
            "tree": git(candidate, "rev-parse", "HEAD^{tree}"), "base": base, "head": head,
            "reason": "ordinary-markdown-only" if docs else "application-build-required"}


def verify_jobs(needs, source):
    require(isinstance(needs, dict) and set(needs) == JOBS, "incomplete qualification dependencies")
    require(needs["route"].get("result") == "success", "routing did not succeed")
    outputs = needs["route"].get("outputs", {})
    require(outputs.get("source") == source and SHA.fullmatch(source), "route source mismatch")
    require(SHA.fullmatch(outputs.get("tree", "")), "missing candidate tree")
    required = outputs.get("required")
    require(required in {"true", "false"}, "missing build decision")
    require(outputs.get("reason") == ("application-build-required" if required == "true"
                                      else "ordinary-markdown-only"), "route reason mismatch")
    for name in ("host", "qt", "client"):
        expected = "success" if required == "true" else "skipped"
        require(needs[name].get("result") == expected,
                f"{name}: expected {expected}, received {needs[name].get('result', 'missing')}")
    return outputs


def verify_build_execution(jobs, run_id, attempt, head):
    """An overall green reusable job cannot hide skipped compile/package steps."""
    names = {"iOS host contracts", "qt / qt-ios-source", "client / Host contracts",
             "client / Static JITless V8 checkpoint", "client / Toolchain, dependencies, build and package"}
    selected = [job for job in jobs if job.get("name") in names]
    require(len(selected) == len(names) and {job["name"] for job in selected} == names,
            "missing or duplicate selected build jobs")
    for job in selected:
        require(job.get("run_id") == run_id and job.get("run_attempt") == attempt
                and job.get("head_sha") == head, "job belongs to another run, attempt or PR head")
        require(job.get("status") == "completed" and job.get("conclusion") == "success",
                f"selected job did not succeed: {job['name']}")
        if job["name"].endswith("Toolchain, dependencies, build and package"):
            for name in ("Build experimental full client", "Verify required Interface QML plugins in full-client link",
                         "Package numbered unsigned client IPA", "Upload short-lived unsigned E2E client handoff"):
                matches = [step for step in job.get("steps", []) if step.get("name") == name]
                require(len(matches) == 1 and matches[0].get("conclusion") == "success",
                        f"selected build step missing, skipped or failed: {name}")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_ipa(directory, source, build_number):
    manifests = list(directory.rglob("*-OverteIOSClient-Release-device-unsigned.json"))
    ipas = list(directory.rglob("*.ipa"))
    require(len(manifests) == len(ipas) == 1, "expected one full-client IPA and manifest")
    manifest_path, ipa = manifests[0], ipas[0]
    require(not manifest_path.is_symlink() and not ipa.is_symlink(), "symlink artifact")
    manifest = json.loads(manifest_path.read_text())
    expected = {"schemaVersion": 1, "product": "overte-ios-integrated-client",
                "sourceRevision": source, "platform": "iphoneos", "architecture": "arm64",
                "configuration": "Release", "testBuildContractVersion": 1,
                "signed": False, "requiresSigning": True}
    for key, value in expected.items():
        require(manifest.get(key) == value and type(manifest.get(key)) is type(value),
                f"manifest {key} mismatch")
    require(type(manifest.get("buildNumber")) is int and manifest["buildNumber"] == build_number,
            "manifest build number mismatch")
    require(manifest.get("artifact") == ipa.name and manifest.get("manifest") == manifest_path.name,
            "manifest filename mismatch")
    digest = sha256(ipa)
    require(manifest.get("sha256") == digest, "IPA digest mismatch")
    with zipfile.ZipFile(ipa) as archive:
        entries = archive.infolist()
        require(len({item.filename for item in entries}) == len(entries), "duplicate IPA entries")
        info_entries = [item for item in entries
                        if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", item.filename)]
        require(len(info_entries) == 1 and info_entries[0].file_size < 1024 * 1024,
                "missing or oversized outer app Info.plist")
        info = plistlib.loads(archive.read(info_entries[0]))
        require(info.get("CFBundleIdentifier") == "org.overte.interface.e2e", "wrong app identity")
        require(info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"], "not a physical-device IPA")
        contract = info.get("OverteE2ETestBuildContractVersion")
        require(type(contract) is int and contract == 1, "missing embedded E2E contract")
        executable = info.get("CFBundleExecutable", "")
        require(executable and PurePosixPath(executable).name == executable, "invalid executable name")
        binary = archive.getinfo(str(PurePosixPath(info_entries[0].filename).parent / executable))
        require(binary.file_size > 4096 and not stat.S_ISLNK(binary.external_attr >> 16),
                "missing full-client executable")
        with archive.open(binary) as stream:
            header = stream.read(8)
        require(header[:4] == b"\xcf\xfa\xed\xfe" and header[4:8] == b"\x0c\x00\x00\x01",
                "app executable is not an arm64 Mach-O")
    return {"artifact": ipa.name, "manifest": manifest_path.name, "sha256": digest,
            "version": info.get("CFBundleShortVersionString"), "appBuild": info.get("CFBundleVersion")}


def report(needs, source, build_number, run_id, attempt, directory, jobs):
    outputs = verify_jobs(needs, source)
    required = outputs["required"] == "true"
    require(all(type(value) is int and value > 0 for value in (build_number, run_id, attempt)),
            "invalid run identity")
    if required:
        verify_build_execution(jobs, run_id, attempt, outputs.get("head", source))
    artifact = verify_ipa(directory, source, build_number) if required else None
    return {"schema": 1, "repository": REPOSITORY, "repositoryId": REPOSITORY_ID,
            "context": CONTEXT, "sourceRevision": source, "sourceTree": outputs["tree"],
            "baseRevision": outputs.get("base"), "headRevision": outputs.get("head"),
            "runId": run_id, "runAttempt": attempt, "buildNumber": build_number,
            "checks": "passed", "ipa": "verified" if required else "not-required",
            "reason": outputs["reason"], "artifact": artifact,
            "installation": "not-performed", "deviceAcceptance": "not-performed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("route")
    plan.add_argument("--event", type=Path, required=True)
    plan.add_argument("--candidate", type=Path, required=True)
    plan.add_argument("--sha", required=True)
    plan.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--needs", type=Path, required=True)
    check.add_argument("--jobs", type=Path, required=True)
    check.add_argument("--source", required=True)
    check.add_argument("--build-number", type=int, required=True)
    check.add_argument("--run-id", type=int, required=True)
    check.add_argument("--attempt", type=int, required=True)
    check.add_argument("--artifacts", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "route":
            event = json.loads(args.event.read_text())
            result = route(event, args.candidate, args.sha)
            validate_wiring(args.candidate, event)
            with args.output.open("a") as handle:
                handle.write("".join(f"{key}={value}\n" for key, value in result.items()))
        else:
            result = report(json.loads(args.needs.read_text()), args.source, args.build_number,
                            args.run_id, args.attempt, args.artifacts, json.loads(args.jobs.read_text()))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
                    summary.write(f"## iOS qualification\n\nSource: `{result['sourceRevision']}`\n\n"
                                  f"Checks: **{result['checks']}**; IPA: **{result['ipa']}**; "
                                  "installation: **not performed**; device acceptance: **not performed**.\n")
                    if result["artifact"]:
                        summary.write(f"\nIPA SHA-256: `{result['artifact']['sha256']}`\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError,
            zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print(f"iOS build qualification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
