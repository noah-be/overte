#!/usr/bin/env python3
"""Trusted iOS merge-candidate routing and physical-device artifact verification."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
CONTEXT = "ios-device-build"
JOBS = {"route", "host", "qt", "client"}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    return subprocess.check_output(["git", "--no-replace-objects", *args], cwd=root, text=True,
                                   stderr=subprocess.PIPE, timeout=30).strip()


def configuration(policy_root=ROOT):
    config = json.loads((policy_root / ".github/ios-build-qualification.json").read_text())
    require(config.get("schema") == 1 and config.get("repository") == REPOSITORY
            and config.get("repositoryId") == REPOSITORY_ID
            and config.get("requiredContext") == CONTEXT
            and type(config.get("enforceWorkflow")) is bool
            and config.get("workflowPath") == ".github/workflows/ios-build-qualification.yml"
            and type(config.get("inputSelection", False)) is bool,
            "invalid trusted build qualification policy")
    return config


def input_selector(policy_root=ROOT):
    """Load only the reviewed policy checkout; candidate contents are Git data."""
    path = policy_root / "tools/ios-build-qualification/inputs.py"
    require(path.is_file() and not any(parent.is_symlink() for parent in
            (policy_root / "tools", path.parent, path)), "trusted iOS input selector unavailable")
    spec = importlib.util.spec_from_file_location("trusted_ios_application_inputs", path)
    require(spec is not None and spec.loader is not None, "trusted iOS input selector unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def host_handoff(policy_root=ROOT):
    """Older explicit policy fixtures retain their exact legacy protocol."""
    if not (policy_root / ".github/ios-host-orchestration.json").is_file():
        return None
    path = ROOT / "tools/ios-build-qualification/host.py"
    spec = importlib.util.spec_from_file_location("trusted_ios_host_handoff", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def fresh_host_candidate(event, candidate, source, *, policy_root=ROOT):
    """Next-generation PRs require live bookends; manual routes remain full."""
    handoff = host_handoff(policy_root)
    selected = (handoff is not None and event is not None and candidate is not None
                and event.get("pull_request") is not None
                and handoff.participates(candidate, source, event, policy_root=policy_root))
    if not selected:
        yield
        return
    before = handoff.fresh_context(event, candidate, source, policy_root=policy_root)
    yield
    require(handoff.fresh_context(event, candidate, source, policy_root=policy_root) == before,
            "current iOS PR metadata changed during trusted verification")


def validate_wiring(candidate, event, policy_root=ROOT):
    """Called by the independently required, default-branch repository router.

    This prevents a PR from making the final build check optional/skipped or
    replacing its verifier. The flag is staged off until the workflow is deployed.
    """
    if event.get("pull_request", {}).get("base", {}).get("ref") != "apple-ios":
        return
    handoff = host_handoff(policy_root)
    source = git(candidate, "rev-parse", "HEAD") if handoff is not None and (candidate / ".git").exists() else None
    if source is not None and handoff.participates(candidate, source, event, policy_root=policy_root):
        handoff.route(event, candidate, source, policy_root=policy_root)
        return
    config = configuration(policy_root)
    path = candidate / config["workflowPath"]
    if not path.exists() and not config["enforceWorkflow"]:
        return
    require(path.is_file() and not path.is_symlink(), "required iOS qualification workflow missing")
    canonical = (policy_root / "tools/ios-build-qualification/workflow.yml").read_text()
    require(path.read_text() == canonical,
            "iOS build workflow differs from trusted orchestration; update the parent policy first")


def route(event, candidate, expected_sha, *, policy_root=ROOT):
    config = configuration(policy_root)
    repo = event["repository"]
    require(repo["full_name"] == REPOSITORY and repo["id"] == REPOSITORY_ID,
            "foreign repository")
    require(SHA.fullmatch(expected_sha), "invalid candidate revision")
    require(git(candidate, "rev-parse", "HEAD") == expected_sha, "wrong candidate checkout")
    handoff = host_handoff(policy_root)
    if handoff is not None and handoff.participates(candidate, expected_sha, event, policy_root=policy_root):
        return handoff.route(event, candidate, expected_sha, policy_root=policy_root)
    pr = event.get("pull_request")
    if pr:
        require(pr["base"]["ref"] == "apple-ios", "qualification target must be apple-ios")
        for side in ("base", "head"):
            require(pr[side]["repo"]["full_name"] == REPOSITORY
                    and pr[side]["repo"]["id"] == REPOSITORY_ID, "foreign PR source")
        spec = importlib.util.spec_from_file_location("ios_candidate_context", ROOT / "tools/repository-checks/check.py")
        checks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checks)
        resolved = checks.pr_candidate_context(candidate, event, expected_sha)
        base, head = resolved["base"], resolved["head"]
        tree = git(candidate, "rev-parse", expected_sha + "^{tree}")
        if tree == git(candidate, "rev-parse", base + "^{tree}") == git(candidate, "rev-parse", head + "^{tree}"):
            return {"required": "false", "source": expected_sha, "tree": tree,
                    "base": base, "head": head, "reason": "unchanged-tree"}
        if config.get("inputSelection", False):
            selection = input_selector(policy_root).candidate_plan(candidate, base, expected_sha)
            required = selection["requires_application_build"]
            return selected_route(selection, expected_sha, base, head, required)
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
        if config.get("inputSelection", False):
            selection = {"reason": "manual-application-build-required", "requires_application_build": True,
                         "candidate": input_selector(policy_root).input_fingerprint(candidate, expected_sha)}
            return selected_route(selection, expected_sha, base, head, True)
    return {"required": "false" if docs else "true", "source": expected_sha,
            "tree": git(candidate, "rev-parse", "HEAD^{tree}"), "base": base, "head": head,
            "reason": "ordinary-markdown-only" if docs else "application-build-required"}


def selected_route(selection, source, base, head, required):
    # Actual iOS host inputs are still application inputs. An independent shared
    # owner must eventually establish host-only CI evidence; there is no green
    # delegation receipt in this dormant compatibility implementation.
    value = {"selection": selection, "router": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {"required": str(required).lower(), "host_required": str(required).lower(),
            "source": source, "tree": selection["candidate"]["tree"], "base": base, "head": head,
            "reason": selection["reason"], "selection": "sha256:" + digest}


def verify_jobs(needs, source, *, event=None, candidate=None, policy_root=ROOT):
    enabled = configuration(policy_root).get("inputSelection", False)
    require(isinstance(needs, dict) and set(needs) == JOBS, "incomplete qualification dependencies")
    require(needs["route"].get("result") == "success", "routing did not succeed")
    outputs = needs["route"].get("outputs", {})
    handoff = host_handoff(policy_root)
    next_generation = "generation" in outputs or handoff is not None and event is not None and candidate is not None \
        and handoff.participates(candidate, source, event, policy_root=policy_root)
    if next_generation:
        require(handoff is not None and event is not None and candidate is not None,
                "iOS host selection requires the independent event and exact candidate")
        expected = handoff.route(event, candidate, source, policy_root=policy_root)
        require(outputs == expected, "iOS host route differs from the independently recomputed candidate")
        for name in ("host", "qt", "client"):
            selected = expected["host_required" if name == "host" else "required"] == "true"
            require(needs[name].get("result") == ("success" if selected else "skipped"),
                    "iOS next-generation selected job failed, was skipped or was unexpectedly present: " + name)
        return outputs
    require(outputs.get("source") == source and SHA.fullmatch(source), "route source mismatch")
    require(SHA.fullmatch(outputs.get("tree", "")), "missing candidate tree")
    required = outputs.get("required")
    require(required in {"true", "false"}, "missing build decision")
    unchanged = outputs.get("reason") == "unchanged-tree"
    if unchanged:
        require(event is not None and candidate is not None,
                "unchanged-tree verification requires the independent event and candidate metadata")
        expected = route(event, candidate, source, policy_root=policy_root)
        require(expected.get("reason") == "unchanged-tree" and outputs == expected,
                "unchanged-tree result differs from the independent exact candidate")
        host_required = False
    elif enabled:
        require(event is not None and candidate is not None,
                "input selection verification requires the independent event and candidate checkout")
        validate_wiring(candidate, event, policy_root)
        expected = route(event, candidate, source, policy_root=policy_root)
        require(outputs == expected, "route source, selection or decision differs from the independent candidate plan")
        host_required = expected["host_required"] == "true"
    else:
        require(outputs.get("reason") == ("application-build-required" if required == "true"
                                          else "ordinary-markdown-only"), "route reason mismatch")
        host_required = required == "true"
    for name in ("host", "qt", "client"):
        selected = host_required if name == "host" else required == "true"
        expected = "success" if selected else "skipped"
        require(needs[name].get("result") == expected,
                f"{name}: expected {expected}, received {needs[name].get('result', 'missing')}")
    if enabled and not unchanged:
        require(required == "true", "lightweight input selection requires an independently authenticated shared host owner; "
                "that integration is not active")
    return outputs


@contextmanager
def verification_candidate(needs, source, *, event=None, candidate=None):
    """Supply commit metadata for the deployed legacy final verifier, never code.

    Its workflow already passes the exact source and receives the trusted route
    outputs, but does not check out the candidate or pass the event explicitly.
    Only a claimed unchanged tree needs this extra, independent metadata read.
    """
    unchanged = needs.get("route", {}).get("outputs", {}).get("reason") == "unchanged-tree"
    if not unchanged or event is not None and candidate is not None:
        yield event, candidate
        return
    require(event is None and candidate is None, "incomplete independent unchanged-tree context")
    require(SHA.fullmatch(source), "invalid unchanged-tree candidate")
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    require(event_path.is_file() and not event_path.is_symlink() and event_path.stat().st_size <= 2_000_000,
            "independent GitHub event is unavailable")
    event = json.loads(event_path.read_text())
    # A fresh bare repository has no checkout, hooks, candidate imports or
    # executable files. Fetch only commit/tree metadata from the fixed fork.
    environment = {"PATH": os.defpath, "HOME": "/nonexistent", "GIT_TERMINAL_PROMPT": "0",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    with tempfile.TemporaryDirectory(prefix="overte-ios-noop-") as temporary:
        metadata = Path(temporary)
        try:
            for command in (["init", "-q", "--bare"],
                            ["-c", "gc.auto=0", "-c", "maintenance.auto=false", "fetch", "--quiet",
                             "--no-tags", "--depth=2", "--filter=blob:none",
                             "https://github.com/noah-l-frank/overte.git", source],
                            ["update-ref", "HEAD", source]):
                subprocess.run(["git", "--no-replace-objects", *command], cwd=metadata,
                               env=environment, check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=45)
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("independent unchanged-tree Git metadata is unavailable") from error
        yield event, metadata


def verify_build_execution(jobs, run_id, attempt, head):
    """An overall green reusable job cannot hide skipped compile/package steps."""
    require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0
            and isinstance(head, str) and SHA.fullmatch(head), "invalid qualifier identity")
    names = {"iOS host contracts", "qt / qt-ios-source", "client / Host contracts",
             "client / Static JITless V8 checkpoint", "client / Toolchain, dependencies, build and package"}
    selected = [job for job in jobs if job.get("name") in names]
    require(len(selected) == len(names) and {job["name"] for job in selected} == names,
            "missing or duplicate selected build jobs")
    ids = [job.get("id") for job in selected]
    require(all(type(value) is int and value > 0 for value in ids) and len(set(ids)) == len(ids),
            "missing or duplicate actual producer job IDs")
    snapshot_attempt = selected[0].get("run_attempt")
    require(type(snapshot_attempt) is int and snapshot_attempt > 0
            and all(type(job.get("run_attempt")) is int and job["run_attempt"] == snapshot_attempt
                    for job in selected), "selected producer jobs have inconsistent attempts")
    # A failed-only retry can retain earlier API records or create new snapshot
    # IDs/attempt fields carrying the original successful execution timestamps.
    # This field is API snapshot identity, not original execution provenance.
    require(snapshot_attempt == attempt or (snapshot_attempt == 1 and attempt == 2),
            "unsupported producer/qualifier attempt ordering")
    for job in selected:
        require(type(job.get("run_id")) is int and job.get("run_id") == run_id
                and job.get("head_sha") == head, "job belongs to another run, attempt or PR head")
        require(job.get("status") == "completed" and job.get("conclusion") == "success",
                f"selected job did not succeed: {job['name']}")
        if job["name"].endswith("Toolchain, dependencies, build and package"):
            for name in ("Build experimental full client", "Verify required Interface QML plugins in full-client link",
                         "Package numbered unsigned client IPA", "Upload short-lived unsigned E2E client handoff"):
                matches = [step for step in job.get("steps", []) if step.get("name") == name]
                require(len(matches) == 1 and matches[0].get("status") == "completed"
                        and matches[0].get("conclusion") == "success",
                        f"selected build step missing, skipped or failed: {name}")
    return {"runId": run_id, "apiSnapshotRunAttempt": snapshot_attempt, "qualifierRunAttempt": attempt,
            "headRevision": head, "apiSnapshotJobIds": ids,
            "originalExecutionRunAttempt": None, "originalExecutionJobIds": None,
            "originalExecutionIdentityVerification": "not-observed-by-legacy-invocation",
            "artifactIdVerification": "not-observed-by-legacy-invocation",
            "originalArtifactZipDigestVerification": "not-observed-by-legacy-invocation"}


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


def report(needs, source, build_number, run_id, attempt, directory, jobs, *, event=None, candidate=None,
           policy_root=ROOT, run_metadata=None):
    outputs = verify_jobs(needs, source, event=event, candidate=candidate, policy_root=policy_root)
    required = outputs["required"] == "true"
    require(all(type(value) is int and value > 0 for value in (build_number, run_id, attempt)),
            "invalid run identity")
    producer = verify_build_execution(jobs, run_id, attempt, outputs.get("head", source)) if required else None
    artifact = verify_ipa(directory, source, build_number) if required else None
    host_producer = None
    if "generation" in outputs and outputs["host_required"] == "true":
        host_producer = host_handoff(policy_root).verify_execution(jobs, run_metadata, run_id, attempt,
                                                                  outputs.get("head", source))
    result = {"schema": 1, "repository": REPOSITORY, "repositoryId": REPOSITORY_ID,
            "context": CONTEXT, "sourceRevision": source, "sourceTree": outputs["tree"],
            "baseRevision": outputs.get("base"), "headRevision": outputs.get("head"),
            "runId": run_id, "runAttempt": attempt, "buildNumber": build_number,
            "producer": producer,
            "checks": "passed", "ipa": "verified" if required else "not-required",
            "reason": outputs["reason"], "artifact": artifact,
            "installation": "not-performed", "deviceAcceptance": "not-performed"}
    if "generation" in outputs:
        result["hostSelection"] = {"generation": outputs["generation"], "plan": outputs["selection"],
            "inputs": outputs["host_inputs"], "applicationBuildRequired": required,
            "iosHostRequired": outputs["host_required"] == "true", "producer": host_producer}
    if outputs["reason"] == "unchanged-tree":
        result["unchangedTreeProof"] = {"tree": outputs["tree"], "base": outputs["base"],
                                        "head": outputs["head"], "candidate": source}
    elif configuration(policy_root).get("inputSelection", False):
        result["inputSelection"] = {"plan": outputs["selection"], "applicationBuildRequired": required,
                                    "iosHostRequired": outputs["host_required"] == "true"}
    return result


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
    check.add_argument("--event", type=Path)
    check.add_argument("--candidate", type=Path)
    check.add_argument("--run-metadata", type=Path)
    check.add_argument("--build-number", type=int, required=True)
    check.add_argument("--run-id", type=int, required=True)
    check.add_argument("--attempt", type=int, required=True)
    check.add_argument("--artifacts", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "route":
            event = json.loads(args.event.read_text())
            with fresh_host_candidate(event, args.candidate, args.sha):
                result = route(event, args.candidate, args.sha)
                validate_wiring(args.candidate, event)
            with args.output.open("a") as handle:
                handle.write("".join(f"{key}={value}\n" for key, value in result.items()))
        else:
            needs = json.loads(args.needs.read_text())
            with verification_candidate(needs, args.source,
                    event=json.loads(args.event.read_text()) if args.event is not None else None,
                    candidate=args.candidate) as (event, candidate):
                with fresh_host_candidate(event, candidate, args.source):
                    result = report(needs, args.source, args.build_number, args.run_id, args.attempt,
                                    args.artifacts, json.loads(args.jobs.read_text()),
                                    event=event, candidate=candidate,
                                    run_metadata=json.loads(args.run_metadata.read_text()) if args.run_metadata else None)
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
