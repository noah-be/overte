"""Bounded archive handling and read-only Full Client artifact inspection."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import sys
import zipfile

from common import ROOT, digest, json_read
from source_checks import PRIVACY_RULES, scan_patterns


def extract_zip(archive: Path, target: Path, max_bytes=8 * 1024**3):
    """Reject traversal, links, collisions, bombs and special files before writing."""
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 200000 or sum(x.file_size for x in z.infolist()) > max_bytes:
            raise ValueError("archive exceeds inspection limits")
        seen = set()
        for item in z.infolist():
            name = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (name.is_absolute() or ".." in name.parts or "\\" in item.filename
                    or ":" in item.filename or not name.parts
                    or item.filename.casefold().rstrip("/") in seen
                    or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("unsafe archive member")
            seen.add(item.filename.casefold().rstrip("/"))
        for item in z.infolist():
            dest = target.joinpath(*PurePosixPath(item.filename).parts)
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as source, dest.open("xb") as out:
                shutil.copyfileobj(source, out, length=1024 * 1024)
            # Preserve executable status, never archive ownership or writable permissions.
            dest.chmod(0o700 if (item.external_attr >> 16) & 0o111 else 0o600)


def tree_digest(app: Path):
    h = hashlib.sha256()
    for path in sorted(app.rglob("*")):
        if path.is_symlink():
            raise ValueError("artifact symlinks are unsupported")
        if path.is_file():
            h.update(str(path.relative_to(app)).encode() + b"\0")
            h.update(("x" if path.stat().st_mode & 0o111 else "-").encode())
            h.update(bytes.fromhex(digest(path)))
    return h.hexdigest()


def select_artifact(ctx):
    if ctx.artifact is not None:
        return ctx.artifact
    name = ctx.config.get("artifact")
    if not ctx.need(name, "artifact-missing", "Provide the candidate .app or .ipa."):
        return None
    path = Path(name).expanduser().resolve()
    if not ctx.need(path.exists(), "artifact-missing", "The selected artifact is unavailable."):
        return None
    if path.is_dir() and path.suffix == ".app":
        actual = tree_digest(path)
        dest = ctx.output / "candidate.app"
        shutil.copytree(path, dest, symlinks=True)
        ctx.need(tree_digest(dest) == actual, "artifact-copy", "App changed during private snapshotting.")
    elif path.is_file() and path.suffix == ".ipa":
        actual = digest(path)
        target = ctx.output / "unpacked"
        target.mkdir(mode=0o700)
        extract_zip(path, target)
        apps = list((target / "Payload").glob("*.app"))
        if not ctx.need(len(apps) == 1, "ipa-app-count", "IPA must contain exactly one top-level application."):
            return None
        dest = apps[0]
        ctx.need(digest(path) == actual, "artifact-race", "IPA changed during inspection.")
    else:
        ctx.add("artifact-format", "FAIL", message="Expected a .app directory or .ipa file.", critical=True)
        return None
    ctx.artifact_sha, ctx.artifact = actual, dest
    ctx.need(actual == ctx.config.get("artifactSha256"), "artifact-binding", "Candidate digest must match the private release configuration.")
    return dest


def artifact(ctx, scope):
    app = select_artifact(ctx)
    if app is None:
        return
    info = plistlib.loads((app / "Info.plist").read_bytes())
    ats = info.get("NSAppTransportSecurity", {})
    ctx.need(not any(ats.get(k) for k in ("NSAllowsArbitraryLoads", "NSAllowsArbitraryLoadsInWebContent", "NSAllowsArbitraryLoadsForMedia")),
             "artifact-ats", "Compiled Info.plist must not introduce a broad ATS bypass.")
    source_info = plistlib.loads((ROOT / "ios/resources/InterfaceInfo.plist.in").read_bytes())
    for key in set(source_info) | set(info):
        if key.endswith("UsageDescription") or key in {"UIBackgroundModes", "UIFileSharingEnabled", "LSSupportsOpeningDocumentsInPlace"}:
            ctx.need(info.get(key) == source_info.get(key), "artifact-privacy-drift", f"Compiled privacy/capability entry differs from reviewed source: {key}")
    executable = info.get("CFBundleExecutable")
    if not ctx.need(executable == "Overte", "full-client-artifact", "Only the Full Client Overte executable is eligible."):
        return
    bundle = ctx.config.get("bundleIdentifier", "")
    ctx.command("client-metadata", [sys.executable, ROOT / "ios/tools/verify-client-bundle-info.py", app,
                                    bundle, "iphoneos", "17.0"])
    ctx.command("privacy-manifest", [sys.executable, ROOT / "ios/tools/verify-privacy-manifest.py", app / "PrivacyInfo.xcprivacy"])
    ctx.command("static-runtime", [sys.executable, ROOT / "ios/tools/verify-ios-static-runtime.py", app])
    ctx.command("no-e2e-contract", [sys.executable, ROOT / "ios/tools/verify-e2e-test-build.py", app / "Info.plist", "--expected", "disabled"])
    ctx.need(not bundle.endswith(".e2e") and ".bootstrap" not in bundle, "product-identity", "E2E/bootstrap artifacts are not release candidates.")
    for key, expected in (("CFBundleShortVersionString", ctx.config.get("marketingVersion")),
                          ("CFBundleVersion", ctx.config.get("buildNumber"))):
        ctx.need(expected and str(info.get(key)) == str(expected), "artifact-" + key, f"Artifact {key} must match the intended release.")
    rows, manifests, binaries = [], [], []
    file_hashes = {}
    forbidden = re.compile(r"(?i)(?:^|/)(?:\.git|DerivedData|xcuserdata|__pycache__)(?:/|$)|\.(?:p12|pfx|key|pem|log|dmp|crash|dSYM|o|a|pyc|bak|tmp)$")
    for path in sorted(app.rglob("*")):
        if not path.is_file():
            continue
        name = str(path.relative_to(app))
        size = path.stat().st_size
        sha = digest(path)
        file_hashes[name] = sha
        rows.append({"file": name, "size": size, "sha256": sha, "executable": bool(path.stat().st_mode & 0o111)})
        if forbidden.search(name) or ".dSYM/" in name:
            ctx.add("artifact-residue", "FAIL", name, message="Private, debug, build or temporary payload in app.", critical=True,
                    evidence=sha, suppressible=True)
        if re.search(r"(?i)testdata|screenshot|fixture|mock|backup", name):
            ctx.add("artifact-test-asset", "WARNING", name, message="Review potentially unintended test/developer asset.", evidence=sha, suppressible=True)
        if size > 50 * 1024 * 1024:
            ctx.add("artifact-large-file", "WARNING", name, message=f"Large bundled file: {size} bytes.", next_step="Confirm runtime need and size budget.")
        if path.name == "PrivacyInfo.xcprivacy":
            manifests.append({"file": name, "value": plistlib.loads(path.read_bytes())})
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
            binaries.append(name)
            ctx.command("arch-" + sha[:12], ["xcrun", "lipo", "-verify_arch", "arm64", path])
            loads = ctx.command("loads-" + sha[:12], ["xcrun", "otool", "-l", path])
            if loads and b"__DWARF" in loads.stdout:
                ctx.add("embedded-dwarf", "FAIL", name, message="Release contains embedded DWARF sections.", critical=True)
            if name != executable:
                ctx.add("unexpected-executable", "FAIL", name, message="Additional Mach-O executable/library requires a reviewed exception under the static-runtime policy.",
                        critical=True, evidence=sha, suppressible=True)
        elif path.stat().st_mode & 0o111:
            ctx.add("executable-resource", "WARNING", name, message="Non-Mach-O resource has executable permissions.")
        # Bounded streaming scan includes binary ASCII/UTF-16LE strings. Overlap catches boundary secrets.
        with path.open("rb") as stream:
            tail = b""
            offset = 0
            seen_rules = set()
            while block := stream.read(1024 * 1024):
                data = tail + block
                strings = data.decode("utf-8", errors="replace") + "\n" + data.decode("utf-16le", errors="replace")
                for rule, status, pattern in PRIVACY_RULES:
                    if rule not in seen_rules and re.search(pattern, strings):
                        seen_rules.add(rule)
                        ctx.add("artifact-" + rule, status, name, message=f"Sensitive string candidate near byte block {offset}; value omitted.",
                                next_step="Inspect privately, strip unnecessary data or record an exact reviewed exception.",
                                critical=status == "FAIL", evidence=sha, suppressible=True)
                if re.search(r"OverteTabletScreen\.|OverteTabletControl\.|OverteE2E", strings) and "e2e" not in seen_rules:
                    seen_rules.add("e2e")
                    ctx.add("artifact-e2e-marker", "FAIL", name, message="Test automation marker in production payload.", critical=True)
                tail, offset = data[-4096:], offset + len(block)
    ctx.inventories["artifact-files"] = rows
    ctx.inventories["artifact-privacy-manifests"] = manifests
    ctx.inventories["artifact-binaries"] = binaries
    ctx.need(executable in binaries, "macho-executable", "The selected application executable must be a supported Mach-O image.")
    scanner_report = ctx.output / "gitleaks-artifact.private.json"
    scan = ctx.command("gitleaks-artifact", ["gitleaks", "dir", app, "--redact=100", "--ignore-gitleaks-allow",
                        "--config", Path(__file__).parent / "gitleaks.toml", "--exit-code", "42",
                        "--report-format", "json", "--report-path", scanner_report], timeout=3600, ok=(0, 42))
    if scan and scan.returncode in (0, 42):
        leaks = json_read(scanner_report) if scanner_report.exists() else []
        ctx.need(scan.returncode == 0 or leaks, "artifact-scanner-report", "Scanner reported leaks without structured findings.")
        for item in leaks:
            name = item.get("File", "")
            if Path(name).is_absolute() and Path(name).is_relative_to(app):
                name = str(Path(name).relative_to(app))
            rule = item.get("RuleID", "unknown")
            level = "WARNING" if rule.startswith("ios-private-") else "FAIL"
            ctx.add("artifact-gitleaks-" + rule, level, name, item.get("StartLine", 0),
                    "Potential sensitive content; matched values omitted.",
                    evidence=file_hashes.get(name, ""), suppressible=True, critical=level == "FAIL")
    ctx.review("artifact-content", "Review packed RCC resources, images/OCR, third-party manifests, binary provenance and embedded attribution.", artifact=True)
    for framework in app.rglob("*.framework"):
        if not list(framework.rglob("PrivacyInfo.xcprivacy")):
            ctx.add("sdk-privacy-manifest", "WARNING", str(framework.relative_to(app)), message="Embedded SDK has no privacy manifest; verify whether one is required for this SDK/API use.")
    inspect_signature(ctx, app, info)


def inspect_signature(ctx, app, info):
    mode = ctx.config.get("distribution", "sideload-unsigned")
    signed = (app / "_CodeSignature/CodeResources").exists()
    provision = app / "embedded.mobileprovision"
    if mode == "sideload-unsigned" and not signed:
        ctx.add("unsigned-handoff", "WARNING", message="Unsigned sideload handoff; final re-signed IPA requires a new artifact/signing inspection.")
        ctx.need(not provision.exists(), "unsigned-profile", "Unsigned handoff must not embed a private provisioning profile.")
        return
    if not ctx.need(signed, "signature-required", "Selected distribution requires a verifiable signature."):
        return
    ctx.command("signature", ["codesign", "--verify", "--deep", "--strict", app])
    result = ctx.command("entitlements", ["codesign", "--display", "--entitlements", ":-", app])
    if result is None or result.returncode:
        return
    ent = plistlib.loads(result.stdout)
    ctx.inventories["artifact-entitlements"] = ent
    if ent.get("get-task-allow") is True:
        ctx.add("signed-debug-entitlement", "FAIL" if mode in {"app-store", "ad-hoc"} else "WARNING",
                message="Signed candidate permits debugger attachment.", critical=mode in {"app-store", "ad-hoc"})
    ctx.need(ent.get("application-identifier", "").endswith("." + info["CFBundleIdentifier"]),
             "signed-app-id", "Signed application identifier must match the bundle.")
    if not ctx.need(provision.exists(), "profile-required", "A provisioned signed IPA is required before distribution."):
        return
    decoded = ctx.command("profile", ["security", "cms", "-D", "-i", provision])
    if decoded is None or decoded.returncode:
        return
    profile = plistlib.loads(decoded.stdout)
    expiry = profile.get("ExpirationDate")
    ctx.need(isinstance(expiry, dt.datetime) and expiry.replace(tzinfo=dt.timezone.utc) > dt.datetime.now(dt.timezone.utc),
             "profile-expired", "Provisioning profile must be unexpired.")
    allowed = profile.get("Entitlements", {})
    ctx.need(ent.get("com.apple.developer.team-identifier") in profile.get("TeamIdentifier", []),
             "profile-team", "Signature and profile teams must agree.")
    import fnmatch
    for key, value in ent.items():
        permitted = allowed.get(key)
        def matches(item, expected):
            return fnmatch.fnmatchcase(item, expected) if isinstance(item, str) and isinstance(expected, str) else item == expected
        valid = (all(any(matches(v, a) for a in permitted) for v in value)
                 if isinstance(value, list) and isinstance(permitted, list) else matches(value, permitted))
        ctx.need(valid, "profile-entitlement", f"Profile must authorize signed entitlement: {key}")
    if mode == "app-store":
        ctx.need(not profile.get("ProvisionedDevices") and not profile.get("ProvisionsAllDevices")
                 and allowed.get("get-task-allow") is not True,
                 "store-profile", "Development, ad-hoc and enterprise profiles cannot satisfy the App Store profile gate.")
    elif mode == "ad-hoc":
        ctx.need(bool(profile.get("ProvisionedDevices")) and not profile.get("ProvisionsAllDevices")
                 and allowed.get("get-task-allow") is not True,
                 "ad-hoc-profile", "Ad-hoc distribution requires a device-limited non-debug provisioning profile.")


def distribution(ctx, scope):
    app = select_artifact(ctx)
    if app is None:
        return
    ctx.need(ctx.config.get("distribution") in {"sideload-unsigned", "development-signed", "ad-hoc", "app-store"},
             "distribution-method", "An explicit supported distribution method is required.")
    info = plistlib.loads((app / "Info.plist").read_bytes())
    ctx.need(re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+){2,}", info.get("CFBundleIdentifier", "")),
             "bundle-id", "A valid explicit bundle identifier is required.")
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        ctx.need(re.fullmatch(r"\d+(?:\.\d+){0,2}", str(info.get(key, ""))), "version-" + key, f"Invalid {key}.")
    prior = ctx.config.get("previousBuildNumber")
    def version(value):
        return tuple((list(map(int, str(value).split("."))) + [0, 0])[:3])
    ctx.need(prior is not None and version(info["CFBundleVersion"]) > version(prior),
             "version-monotonic", "Build number must increase from the previous distributed release (use 0 for first release).")
    ctx.need(bool(info.get("CFBundleIcons") or info.get("CFBundleIconName")), "compiled-icons", "Compiled app icon metadata is required.")
    ctx.need(bool(info.get("UILaunchScreen") is not None or info.get("UILaunchStoryboardName")), "launch-assets", "Compiled launch configuration is required.")
    for key in ("NSMicrophoneUsageDescription", "NSLocalNetworkUsageDescription"):
        ctx.need(isinstance(info.get(key), str) and len(info[key]) >= 20, "bundled-permission", f"Bundled {key} is missing/unsuitable.")
    if ctx.config.get("distribution") == "app-store":
        ctx.review("app-store-metadata", "Review current Apple submission requirements, privacy answers, SDK signatures and export compliance. No upload is performed.", artifact=True)
    ctx.review("release-acceptance", "Review all warnings, known port limitations, device coverage and the exact distribution candidate.", artifact=True)
