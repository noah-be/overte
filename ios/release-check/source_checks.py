"""Source-level gates. Heuristics are evidence candidates, never legal conclusions."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from common import HERE, ROOT, digest, git, json_read, write_json

PRIVACY_RULES = [
    ("private-key", "FAIL", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    ("credential-literal", "FAIL", r'''(?i)\b(?:api[_-]?key|password|passwd|access[_-]?token|client[_-]?secret)\s*[=:]\s*["'][^"'\s]{8,}["']'''),
    ("authenticated-url", "FAIL", r"https?://[^/\s:@]+:[^/\s@]+@"),
    ("private-ip", "WARNING", r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|127(?:\.\d{1,3}){3})\b|\b(?:fc|fd)[0-9a-f]{2}:[0-9a-f:]+"),
    ("mac-address", "WARNING", r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b"),
    ("developer-path", "WARNING", r"(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+|/private/(?:var|tmp)/[^\s]+)"),
    ("email", "WARNING", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("internal-host", "WARNING", r"(?i)\b(?:https?://)?[a-z0-9.-]+\.(?:local|internal|lan|corp)\b"),
    ("personal-field", "WARNING", r'''(?i)(?:username|user_name|realname|full_name|phone_number|email_address)\s*[=:]\s*["'][^"']+["']'''),
]
CLEANUP_RULES = [
    ("maintenance-marker", "WARNING", r"\b(?:TODO|FIXME|HACK|XXX)\b"),
    ("developer-feature", "WARNING", r"(?i)debug.?menu|test.?account|mock.?data|staging|testserver|quick.?and.?dirty|temporary.?workaround"),
    ("debug-logging", "WARNING", r"\b(?:NSLog|qDebug|printf|console\.log|os_log_debug)\s*\("),
    ("security-bypass", "WARNING", r"ignoreSslErrors|VerifyNone|NSAllowsArbitraryLoads|disable.{0,15}(?:tls|ssl|certificate)|CURLOPT_SSL_VERIFYPEER.{0,15}0"),
    ("commented-code", "WARNING", r"^\s*//\s*(?:if\s*\(|return\s|[\w:]+\([^)]*\);)"),
]
PERMISSIONS = [
    ("Camera", "NSCameraUsageDescription", r"AVCaptureDevice|AVMediaTypeVideo|UIImagePickerControllerSourceTypeCamera|QCamera"),
    ("Microphone", "NSMicrophoneUsageDescription", r"requestRecordPermission|AVAudioSession|AVMediaTypeAudio|AudioInput|QAudioSource"),
    ("Photo library", "NSPhotoLibraryUsageDescription", r"PHPhotoLibrary|PHAsset\b|UIImagePickerControllerSourceTypePhotoLibrary"),
    ("Photo additions", "NSPhotoLibraryAddUsageDescription", r"UIImageWriteToSavedPhotosAlbum|UISaveVideoAtPathToSavedPhotosAlbum"),
    ("Bluetooth", "NSBluetoothAlwaysUsageDescription", r"CBCentralManager|CBPeripheralManager"),
    ("Location", "NSLocationWhenInUseUsageDescription", r"CLLocationManager|requestWhenInUseAuthorization"),
    ("Always location", "NSLocationAlwaysAndWhenInUseUsageDescription", r"requestAlwaysAuthorization"),
    ("Local network", "NSLocalNetworkUsageDescription", r"QUdpSocket|QTcpSocket|NWBrowser|nw_browser_create|Bonjour|NodeList"),
    ("Contacts", "NSContactsUsageDescription", r"CNContactStore|ABAddressBook"),
    ("Calendar", "NSCalendarsFullAccessUsageDescription", r"EKEventStore|requestFullAccessToEvents"),
    ("Calendar write", "NSCalendarsWriteOnlyAccessUsageDescription", r"requestWriteOnlyAccessToEvents"),
    ("Reminders", "NSRemindersFullAccessUsageDescription", r"requestFullAccessToReminders|EKReminder"),
    ("Motion", "NSMotionUsageDescription", r"CMMotionActivityManager|CMPedometer|CMMotionManager"),
    ("Tracking", "NSUserTrackingUsageDescription", r"ATTrackingManager|ASIdentifierManager|advertisingIdentifier"),
    ("Speech", "NSSpeechRecognitionUsageDescription", r"SFSpeechRecognizer"),
    ("Face ID", "NSFaceIDUsageDescription", r"LAPolicyDeviceOwnerAuthenticationWithBiometrics|LABiometryTypeFaceID"),
    ("Health read", "NSHealthShareUsageDescription", r"HKHealthStore"),
    ("Health write", "NSHealthUpdateUsageDescription", r"requestAuthorizationToShareTypes"),
    ("Media library", "NSAppleMusicUsageDescription", r"MPMediaLibrary|MPMediaQuery"),
]
REASONS = {
    "FileTimestamp": r"\b(?:stat|fstat|lstat|getattrlist)\s*\(|fileModificationDate|creationDate|lastModified",
    "SystemBootTime": r"mach_absolute_time|systemUptime|clock_gettime|ProcessInfo.*uptime",
    "DiskSpace": r"\b(?:statfs|statvfs|fstatfs)\s*\(|volumeAvailableCapacity|NSFileSystemFreeSize|QStorageInfo",
    "UserDefaults": r"NSUserDefaults|UserDefaults\b|CFPreferences",
    "ActiveKeyboards": r"activeInputModes",
}


def valid_grype_database(database, now=None):
    if isinstance(database.get("status"), dict):
        database = database["status"]
    try:
        built = dt.datetime.fromisoformat(database.get("built", "").replace("Z", "+00:00"))
        age = (now or dt.datetime.now(dt.timezone.utc)) - built
        fresh = dt.timedelta(0) <= age <= dt.timedelta(hours=120)
    except (ValueError, TypeError):
        return False
    return fresh and database.get("valid") is True and bool(database.get("schemaVersion")) and not database.get("error")


def scan_patterns(ctx, texts, rules, hashes=None):
    for path, text in texts.items():
        for rule, status, pattern in rules:
            rx = re.compile(pattern, re.MULTILINE)
            matches = list(rx.finditer(text))
            if not matches:
                continue
            # One finding per rule/file, with bounded line lists in the private inventory.
            lines = sorted({text.count("\n", 0, m.start()) + 1 for m in matches})
            ctx.inventories.setdefault("pattern-locations", []).append(
                {"group": ctx.group, "rule": rule, "file": path, "lines": lines})
            evidence = (hashes or {}).get(path, hashlib.sha256(text.encode()).hexdigest())
            ctx.add(rule, status, path, lines[0], f"{len(matches)} candidate(s); matched values omitted.",
                    "Confirm reachability and intent; remove the issue or record an exact false-positive disposition.",
                    critical=status == "FAIL", evidence=evidence, suppressible=True)


def gitleaks_evidence(item, mode, file_hash):
    # Directory-mode fingerprints contain the random private staging root. The
    # normalized finding already binds rule/file/line, so bind content here.
    return file_hash if mode == "dir" else item.get("Fingerprint", "") + file_hash


def secrets(ctx, scope):
    scan_patterns(ctx, scope.texts, PRIVACY_RULES, scope.hashes)
    # Use a staging tree so Gitleaks cannot inherit unrelated Android/Pico exclusions.
    with tempfile.TemporaryDirectory(prefix="gitleaks-", dir=ctx.output) as tmp:
        stage = Path(tmp)
        for name in scope.paths:
            source = ROOT / name
            if source.is_file() and not source.is_symlink():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for mode in ("dir", "git"):
            report = ctx.output / f"gitleaks-{mode}.private.json"
            command = ["gitleaks", mode, str(stage if mode == "dir" else ROOT), "--redact=100",
                       "--config", str(HERE / "gitleaks.toml"), "--ignore-gitleaks-allow",
                       "--gitleaks-ignore-path", str(stage / "no-implicit-ignore"),
                       "--report-format", "json", "--report-path", str(report), "--exit-code", "42"]
            if mode == "git":
                if not ctx.need(git("rev-parse", "--is-shallow-repository").strip() == "false",
                                "history-shallow", "Full reachable HEAD history is required."):
                    continue
                command += ["--log-opts=HEAD -- ios interface libraries cmake scripts plugins/opusCodec plugins/pcmCodec macos/conan CMakeLists.txt conanfile.py .github/workflows/ios-* tests/device"]
            result = ctx.command("gitleaks-" + mode, command, timeout=7200, ok=(0, 42))
            if result is None or result.returncode not in (0, 42):
                continue
            findings = json_read(report) if report.exists() else []
            if result.returncode == 42 and not findings:
                ctx.add("gitleaks-report", "FAIL", message="Scanner detected leaks but produced no findings.", critical=True)
            for item in findings:
                name = item.get("File", "")
                if mode == "dir" and Path(name).is_absolute():
                    name = str(Path(name).relative_to(stage))
                rule_id = item.get("RuleID", "unknown")
                is_private = rule_id.startswith("ios-private-")
                ctx.add("gitleaks-" + rule_id, "WARNING" if is_private else "FAIL", name,
                        item.get("StartLine", 0), "Potential secret detected; inspect private diagnostics.",
                        "Rotate exposed secrets; investigate history; allowlist only verified false positives.",
                        critical=not is_private, evidence=gitleaks_evidence(item, mode, scope.hashes.get(name, "")),
                        suppressible=True)
            # Raw scanner reports may contain author metadata despite --redact.
            if report.exists():
                report.chmod(0o600)
    ctx.review("privacy-content", "Review screenshots, test data, logs, personal information and binary/OCR blind spots.")


def hygiene(ctx, scope):
    suspicious = re.compile(r"(?i)(?:^|/)(?:DerivedData|xcuserdata|\.DS_Store|core\.\d+)(?:/|$)|\.(?:ipa|p12|pfx|mobileprovision|key|pem|log|dmp|crash|bak|tmp|swp|xcuserstate)$")
    for name in scope.paths:
        if suspicious.search(name):
            ctx.add("repository-private-file", "FAIL", name, message="Tracked or unignored private/build residue candidate.",
                    next_step="Remove from source control or review an exact fixture exception.",
                    critical=True, evidence=scope.hashes.get(name, ""), suppressible=True)
        if (ROOT / name).is_symlink():
            inside = (ROOT / name).resolve().is_relative_to(ROOT)
            ctx.add("source-symlink", "WARNING" if inside else "FAIL", name,
                    message="Review source symlink; references outside the checkout are blocked.", critical=not inside)
    for pattern in ("DerivedData/", "xcuserdata/", "build-ios/", "*.ipa", "*.mobileprovision", "*.p12"):
        example = "ios/" + pattern.replace("*", "release-check-example")
        result = ctx.command("ignore-" + hashlib.sha256(pattern.encode()).hexdigest()[:8],
                             ["git", "check-ignore", "--no-index", "--quiet", example], ok=(0, 1), log=False)
        if result and result.returncode == 1:
            ctx.add("gitignore-gap", "WARNING", ".gitignore", message=f"No ignore rule for {pattern}.",
                    next_step="Consider a narrowly scoped ignore rule; ignored files must still not be packaged.")
    scan_patterns(ctx, scope.production_texts(), CLEANUP_RULES, scope.hashes)


def licenses(ctx, scope):
    license_files = [p for p in scope.paths if re.search(r"(?i)(?:license|copying|notice|attribution|copyright)", Path(p).name)]
    ctx.need("LICENSE" in scope.paths and (ROOT / "LICENSE").is_file(), "root-license", "Overte license must exist.")
    root_license = "Apache-2.0" if "Apache License version 2.0" in scope.texts.get("LICENSE", "") else "UNKNOWN"
    ctx.need(root_license != "UNKNOWN", "root-license-review", "Root license declaration differs from the reviewed Overte baseline.")
    assets, rows, branding = [], [], []
    asset_ext = {".png", ".jpg", ".jpeg", ".svg", ".ktx", ".ttf", ".otf", ".wav", ".mp3", ".ogg", ".fbx", ".gltf", ".glb", ".obj", ".fst"}
    attributions = json_read(HERE / "attributions.json")["entries"]
    for name in scope.paths:
        path = Path(name)
        if path.suffix.lower() not in asset_ext:
            continue
        record = attributions.get(name, {})
        valid = (record.get("sha256") == scope.hashes.get(name) and record.get("license")
                 and record.get("source") and record.get("copyright") and record.get("noticeFile")
                 and record["noticeFile"] in scope.paths)
        row = {"file": name, "sha256": scope.hashes.get(name), "status": "PASS" if valid else "WARNING",
               "license": record.get("license", "UNKNOWN"), "provenance": record.get("source", "UNKNOWN"),
               "copyright": record.get("copyright", "UNKNOWN"), "noticeFile": record.get("noticeFile"),
               "nearbyLicenseCandidates": [p for p in license_files if Path(p).parent == path.parent]}
        assets.append(row)
        if re.search(r"(?i)overte|hifi|high.?fidelity|vircadia|apple|logo|icon|brand", name):
            branding.append({"file": name, "kind": "asset", "sha256": scope.hashes.get(name)})
    for path, content in scope.production_texts().items():
        spdx = re.findall(r"SPDX-License-Identifier:\s*([^\r\n*]+)", content)
        if Path(path).suffix in {".c", ".cpp", ".h", ".mm", ".m", ".swift", ".js", ".qml"}:
            rows.append({"file": path, "declaredLicenses": sorted(set(x.strip() for x in spdx)),
                         "status": "PASS" if spdx else "WARNING"})
        for match in list(re.finditer(r"\b(?:Overte|Vircadia|High Fidelity|Apple)\b", content))[:1]:
            branding.append({"file": path, "kind": "name", "line": content.count("\n", 0, match.start()) + 1})
    ctx.inventories["licenses"] = {"rootLicense": root_license, "licenseFiles": license_files, "sources": rows, "assets": assets}
    ctx.inventories["branding"] = branding
    unknown = sum(x["status"] != "PASS" for x in assets)
    if unknown:
        ctx.add("asset-provenance", "WARNING", message=f"{unknown} assets lack complete hash-bound attribution records.",
                next_step="Review licenses.json; add verified records to attributions.json. Do not infer asset licenses from the root license.")
    text = ["# License and attribution inventory", "", "This is not a compatibility opinion.", "",
            "| File | License | Provenance | Status |", "| --- | --- | --- | --- |"]
    text += [f"| {x['file']} | {x['license']} | {x['provenance']} | {x['status']} |" for x in assets]
    text += ["", "## Source declarations", ""] + [f"- {x['file']}: {', '.join(x['declaredLicenses']) or 'UNKNOWN'}" for x in rows]
    (ctx.output / "licenses.md").write_text("\n".join(text) + "\n")
    ctx.review("licenses-attribution", "Confirm source, binary, SDK and media licenses, compatibility and bundled attribution obligations.")
    ctx.review("branding", "Review used names, logos and Apple-related artwork; no automated trademark conclusion.")


def dependencies(ctx, scope):
    policy = json_read(ROOT / "ios/dependencies.json")
    refs = []
    for name, text in scope.texts.items():
        if name.endswith("conanfile.py"):
            for match in re.finditer(r'''self\.(?:requires|tool_requires)\(["']([^"']+)["']''', text):
                ref = match.group(1)
                refs.append({"file": name, "reference": ref, "recipePinned": "#" in ref})
                if "#" not in ref:
                    ctx.add("dependency-recipe-unpinned", "WARNING", name,
                            text.count("\n", 0, match.start()) + 1,
                            "A version pin does not pin the Conan recipe/package revision.",
                            "Resolve with a reviewed lockfile and record package/source hashes.")
    binaries = [{"file": p, "sha256": scope.hashes.get(p)} for p in scope.paths
                if Path(p).suffix in {".a", ".dylib", ".so", ".dll", ".zip", ".gz"}
                or ".framework/" in p or ".xcframework/" in p]
    ctx.inventories["dependencies"] = {"declared": refs, "policy": policy, "binaries": binaries,
        "otherManifests": [p for p in scope.paths if Path(p).name in {"Package.resolved", "Package.swift", "Podfile.lock", "Podfile", "conan.lock", "package-lock.json"}]}
    scan_patterns(ctx, scope.texts, [
        ("mutable-download", "WARNING", r"(?i)(?:GIT_TAG\s+(?:main|master|HEAD)|/latest/|git\+https?[^\s]+(?:main|master))"),
        ("download-script", "WARNING", r"\b(?:curl|wget)\s|file\s*\(DOWNLOAD|ExternalProject_Add|FetchContent_Declare|https?://[^\s]+\.(?:zip|tar|gz)"),
        ("download-execute", "FAIL", r"\b(?:curl|wget)\s+[^\n]+\|\s*(?:sh|bash)\b|verify\s*=\s*False"),
    ], scope.hashes)
    graph = getattr(ctx, "generated_conan_graph", None) or ctx.config.get("conanGraph")
    if graph:
        ctx.command("conan-audit", [sys.executable, ROOT / "ios/tools/audit-conan-graph.py", graph])
        sbom = ctx.output / "conan-sbom.cdx.json"
        ctx.command("conan-sbom", [sys.executable, ROOT / "ios/tools/generate-sbom.py", graph,
                                  ROOT / "ios/dependencies.json", sbom])
    elif not ctx.config.get("executeBuild"):
        ctx.add("dependency-graph-missing", "FAIL", message="Provide the resolved iOS Conan graph; source declarations are incomplete.", critical=True)
    sbom_path = ctx.config.get("completeSbom")
    if ctx.need(sbom_path, "complete-sbom", "A complete CycloneDX SBOM including Qt, V8, MoltenVK, transitive dependencies and assets is required."):
        sbom = json_read(Path(sbom_path))
        components = sbom.get("components", [])
        names = {str(x.get("name", "")).lower() for x in components}
        ctx.need(sbom.get("bomFormat") == "CycloneDX" and components, "sbom-format", "SBOM must be a nonempty CycloneDX document.")
        for expected, alternatives in {"qt": {"qt", "qt6"}, "v8": {"v8", "libnode", "node"}, "moltenvk": {"moltenvk"}}.items():
            ctx.need(bool(names & alternatives), "sbom-" + expected, f"SBOM must account for {expected}.")
        for dep in components:
            name = dep.get("name", "unknown")
            if not dep.get("licenses"):
                ctx.add("dependency-license", "FAIL", message=f"Missing dependency license: {name}", critical=True)
            if dep.get("type") not in {"file", "data"} and (not dep.get("version") or not (dep.get("purl") or dep.get("cpe"))):
                ctx.add("vulnerability-identity", "FAIL", message=f"Missing vulnerability-database identity/version: {name}", critical=True)
            if re.search(r"(?i)GPL|AGPL|SSPL|proprietary|unknown", json.dumps(dep.get("licenses", []))):
                ctx.add("license-compatibility", "WARNING", message=f"License needs compatibility review: {name}")
        scanner_env = {k: v for k, v in os.environ.items() if not k.startswith("GRYPE_") or k in {"GRYPE_DB_AUTO_UPDATE", "GRYPE_DB_CACHE_DIR"}}
        scan = ctx.command("grype", ["grype", "--config", str(HERE / "grype.yaml"), "sbom:" + str(Path(sbom_path).resolve()), "--output", "json",
                                     "--fail-on", "high"], timeout=3600, ok=(0, 2), env=scanner_env)
        if scan and scan.returncode in (0, 2):
            data = json.loads(scan.stdout)
            database = data.get("descriptor", {}).get("db", {})
            ctx.need(isinstance(data.get("matches"), list) and valid_grype_database(database),
                     "vulnerability-db", "Scanner must provide a valid database and structured match list.")
            ctx.need(not data.get("ignoredMatches"), "vulnerability-ignored", "No silently ignored vulnerability matches may enter release acceptance.")
            ctx.inventories["vulnerabilities"] = data
            for match in data.get("matches", []):
                vuln = match["vulnerability"]
                ctx.add("vulnerability", "FAIL" if vuln.get("severity", "").lower() in {"high", "critical"} else "WARNING",
                        message=f"{vuln.get('id')} in {match.get('artifact', {}).get('name')}: {vuln.get('severity')}",
                        next_step="Update, remove, or investigate applicability; high/critical findings block.", critical=True)
            if scan.returncode and not data.get("matches"):
                ctx.add("vulnerability-scanner-error", "FAIL", message="Vulnerability scan failed without findings.", critical=True)
        ctx.review("sbom-provenance", "Confirm SBOM completeness and source/binary hashes against the selected artifact.")
        ctx.need(ctx.config.get("reviews", {}).get("sbom-provenance", {}).get("sbomSha256") == digest(Path(sbom_path)),
                 "sbom-review-binding", "SBOM provenance review must bind the exact complete SBOM bytes.")
    ctx.review("dependency-maintenance", "Review outdated/unnecessary packages, binary origins, SDK manifests, mutable downloads and build scripts.")
    if graph:
        resolved_dependency_join(ctx)


def resolved_dependency_join(ctx):
    graph = getattr(ctx, "generated_conan_graph", None) or ctx.config.get("conanGraph")
    if not ctx.need(graph and ctx.config.get("completeSbom"), "resolved-dependency-join", "The actual resolved graph and complete SBOM are required."):
        return
    nodes = json_read(Path(graph)).get("graph", {}).get("nodes", {})
    components = json_read(Path(ctx.config["completeSbom"])).get("components", [])
    identities = {(x.get("name"), x.get("version")) for x in components}
    for node in nodes.values():
        if node.get("context") != "host" or not node.get("ref"):
            continue
        match = re.match(r"([^/]+)/([^@#:%]+)", node["ref"])
        if match and match.group(1) != "overte-ios-dependencies":
            ctx.need(tuple(match.groups()) in identities, "sbom-resolved-package", "The SBOM must include every resolved iOS package at its exact version.")
    ctx.inventories["resolved-graph-binding"] = {"sourceRevision": ctx.revision,
        "graphSha256": digest(Path(graph)), "sbomSha256": digest(Path(ctx.config["completeSbom"]))}


def static(ctx, scope):
    for name, text in scope.texts.items():
        if "/fixtures/" in name or name.startswith("tests/"):
            continue
        path = Path(name)
        try:
            if path.suffix == ".py":
                ast.parse(text, filename=name)
            elif path.suffix == ".json":
                json.loads(text)
            elif path.suffix in {".plist", ".xcprivacy", ".entitlements", ".xml", ".qrc"} or name.endswith(".plist.in"):
                ET.fromstring(text)
        except (ValueError, SyntaxError, ET.ParseError) as error:
            ctx.add("source-syntax", "FAIL", name, getattr(error, "lineno", 0) or 0,
                    "Source/configuration parsing failed.", critical=True)
    native = [p for p in scope.production_texts() if Path(p).suffix in {".cpp", ".c", ".cc", ".cxx"}]
    if ctx.config.get("cleanBuildReceipt"):
        from scope import file_api_scope
        receipt = json_read(Path(ctx.config["cleanBuildReceipt"]))
        if ctx.need(receipt.get("sourceRevision") == ctx.revision, "analysis-scope-revision", "Compiled analysis scope must belong to this revision."):
            file_api_scope(ctx, Path(receipt["buildDirectory"]), Path(receipt["source"]))
            linked = set(ctx.inventories.get("linked-scope", {}).get("sources", []))
            if linked:
                native = [p for p in native if p in linked]
    filelist = ctx.output / "cppcheck-inputs.txt"
    filelist.write_text("\n".join(str(ROOT / p) for p in native) + "\n")
    result = ctx.command("cppcheck", ["cppcheck", "--enable=warning,performance,portability", "--error-exitcode=1",
                             "--xml", "--xml-version=2", "--std=c++20", "--file-list=" + str(filelist)], timeout=7200, ok=(0, 1))
    if result and result.returncode in (0, 1):
        try:
            errors = ET.fromstring(result.stderr).findall("./errors/error")
        except ET.ParseError:
            errors = []
            ctx.add("cppcheck-report-invalid", "FAIL", message="Cppcheck did not produce valid XML; remaining linters will continue.", critical=True)
        ctx.need(result.returncode == 0 or bool(errors), "cppcheck-output", "Analyzer failure must have parseable findings.")
        grouped = {}
        for error in errors:
            location = error.find("location")
            name = location.get("file", "") if location is not None else ""
            if Path(name).is_absolute() and Path(name).is_relative_to(ROOT):
                name = str(Path(name).relative_to(ROOT))
            severity = error.get("severity")
            status = "FAIL" if severity == "error" and name.startswith("ios/") else "WARNING"
            key = (name, error.get("id", "unknown"), status)
            grouped.setdefault(key, []).append(int(location.get("line", "0")) if location is not None else 0)
        for (name, rule, status), lines in grouped.items():
            ctx.add("cppcheck-" + rule, status, name, min(lines),
                    f"{len(lines)} {rule} diagnostic(s); inspect private XML and confirm Release reachability.",
                    evidence=scope.hashes.get(name, ""), suppressible=True, critical=status == "FAIL")
    from linting import run_linters
    run_linters(ctx, scope)
    from scope import swift_scope
    selected_swift, deferred_swift = swift_scope(scope.paths)
    for p in selected_swift:
        ctx.command("swift-" + hashlib.sha256(p.encode()).hexdigest()[:8], ["swiftc", "-frontend", "-parse", p])
    for p in deferred_swift:
        ctx.add("apple-host-tool-deferred", "WARNING", p,
                message="Apple-host helper, not product Swift; parsing is deferred to the macOS clean-build gate.",
                next_step="Run the build group on macOS before release acceptance.")
    ctx.review("static-reachability", "Review conservative C/C++ diagnostics and JS/QML/Metal coverage; the clean-build group separately requires Xcode Objective-C/C++ analysis.")


def plist(ctx, name):
    path = ROOT / name
    try:
        value = plistlib.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise ValueError("plist root")
        return value
    except (OSError, ValueError, plistlib.InvalidFileException):
        ctx.add("plist-invalid", "FAIL", name, message="Required plist is missing or malformed.", critical=True)
        return {}


def configuration(ctx, scope):
    name = "ios/resources/InterfaceInfo.plist.in"
    info = plist(ctx, name)
    for key in ("CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleVersion", "UILaunchScreen",
                "UISupportedInterfaceOrientations", "UISupportedInterfaceOrientations~ipad"):
        ctx.need(key in info, "plist-" + key, f"Required key missing: {key}", name)
    ctx.need(info.get("UIRequiredDeviceCapabilities") == ["arm64"], "device-capabilities", "Review unexpected device requirements.", name)
    ats = info.get("NSAppTransportSecurity", {})
    for key in ("NSAllowsArbitraryLoads", "NSAllowsArbitraryLoadsInWebContent", "NSAllowsArbitraryLoadsForMedia"):
        ctx.need(not ats.get(key), "ats-" + key, "Broad ATS bypass is not release-ready.", name)
    for key in ("NSExceptionDomains", "NSAllowsLocalNetworking"):
        if ats.get(key):
            ctx.add("ats-exception", "WARNING", name, message=f"Review ATS exception: {key}")
    for key in ("UIBackgroundModes", "UIFileSharingEnabled", "LSSupportsOpeningDocumentsInPlace", "LSApplicationQueriesSchemes", "CFBundleURLTypes"):
        if info.get(key):
            ctx.add("capability-review", "WARNING", name, message=f"Review necessity and attack surface: {key}")
    ctx.inventories["configuration"] = {"template": name, "info": info,
        "generator": "CMake Xcode", "target": "Overte", "configuration": "Release",
        "sourceSettings": {p: scope.hashes[p] for p in ("CMakeLists.txt", "interface/CMakeLists.txt", "ios/build-ios.sh", "ios/versions.env")}}
    icon = ROOT / "ios/resources/Assets.xcassets/AppIcon.appiconset/Contents.json"
    if ctx.need(icon.is_file(), "icons", "AppIcon catalog is required."):
        images = json_read(icon).get("images", [])
        ctx.need(bool(images), "icons-empty", "AppIcon catalog cannot be empty.")
        for image in images:
            filename = image.get("filename")
            ctx.need(filename and (icon.parent / filename).is_file(), "icon-file", "Every declared icon slot must resolve to a file.", str(icon.relative_to(ROOT)))


def permissions(ctx, scope):
    info_name = "ios/resources/InterfaceInfo.plist.in"
    info = plist(ctx, info_name)
    rows = []
    texts = {p: t for p, t in scope.production_texts().items() if Path(p).suffix in {".m", ".mm", ".cpp", ".h", ".c", ".swift", ".qml", ".js"}}
    for label, key, pattern in PERMISSIONS:
        uses = []
        for name, text in texts.items():
            for match in re.finditer(pattern, text):
                uses.append({"file": name, "line": text.count("\n", 0, match.start()) + 1})
        description = info.get(key)
        bad_text = description is not None and (not isinstance(description, str) or len(description.strip()) < 20 or re.search(r"(?i)TODO|test|placeholder|lorem|debug", description))
        status = "FAIL" if bad_text else "WARNING" if (uses and not description) or (description and not uses) else "PASS"
        rows.append({"permission": label, "components": uses, "reason": description,
                     "plistEntry": key, "status": status, "reachability": "candidate; review preprocessor conditions and SDK internals"})
        if status != "PASS":
            ctx.add("permission-" + key, status, info_name, message=f"{label}: missing/unused description or unsuitable wording.",
                    next_step="Verify actual iOS reachability; add a clear explanation or remove an unnecessary declaration.", critical=bad_text)
    ctx.inventories["permissions"] = rows
    lines = ["# Permission mapping", "", "| Permission | Using component | Reason | Info.plist entry | Status |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        uses = ", ".join(sorted({x["file"] for x in r["components"]})) or "No source candidate"
        lines.append(f"| {r['permission']} | {uses} | {r['reason'] or 'Not declared'} | {r['plistEntry']} | {r['status']} |")
    (ctx.output / "permissions.md").write_text("\n".join(lines) + "\n")
    manifest_name = "ios/resources/PrivacyInfo.xcprivacy"
    manifest = plist(ctx, manifest_name)
    ctx.command("privacy-contract", [sys.executable, ROOT / "ios/tools/verify-privacy-manifest.py", ROOT / manifest_name])
    declarations = {x.get("NSPrivacyAccessedAPIType"): x.get("NSPrivacyAccessedAPITypeReasons", [])
                    for x in manifest.get("NSPrivacyAccessedAPITypes", [])}
    api_rows = []
    for category, pattern in REASONS.items():
        files = [p for p, text in texts.items() if re.search(pattern, text)]
        reasons = declarations.get("NSPrivacyAccessedAPICategory" + category, [])
        api_rows.append({"category": category, "files": files, "declaredReasons": reasons})
        if files and not reasons:
            ctx.add("required-reason-" + category, "FAIL", manifest_name,
                    message="Potential required-reason API use has no declared category/reason.",
                    next_step="Establish iOS reachability and choose an applicable Apple reason after human review.", critical=True,
                    evidence=digest(ROOT / manifest_name), suppressible=True)
    endpoints, telemetry = [], []
    for path, text in texts.items():
        for match in re.finditer(r"https?://[^\s\"'<>]+", text):
            url = urlsplit(match.group(0))
            endpoints.append({"component": path, "line": text.count("\n", 0, match.start()) + 1,
                              "scheme": url.scheme, "hostname": url.hostname, "data": "Not inferable from URL alone; inspect request construction."})
        for match in re.finditer(r"(?i)analytics|telemetry|crashpad|sentry|firebase|advertisingIdentifier|identifierForVendor|fingerprint|ATTrackingManager|QNetworkAccessManager|sendDatagram|AccountManager", text):
            telemetry.append({"component": path, "line": text.count("\n", 0, match.start()) + 1,
                              "signal": match.group(0), "potentialData": "Review identifiers, account data, logs, voice, world state and metadata at this call site."})
    ctx.inventories["privacy-manifest"] = {"manifest": manifest, "apiCandidates": api_rows}
    ctx.inventories["data-egress"] = {"endpoints": endpoints, "components": telemetry,
        "limits": "Static candidates are not proof of transmitted data or lack of tracking; runtime capture needs a controlled private test account."}
    ctx.review("permissions-privacy", "Confirm permission reachability, explanation quality, required reasons, collected data, tracking declarations and third-party SDK behavior.")
    ctx.review("network-egress", "Review potential data egress and unexpected endpoints against a controlled runtime network observation.")


def signing(ctx, scope):
    name = "ios/resources/Overte.entitlements"
    entitlements = plist(ctx, name)
    ctx.need(entitlements.get("get-task-allow") is not True, "debug-entitlement", "get-task-allow must not be enabled in release source entitlements.", name)
    for key in entitlements:
        ctx.add("entitlement-review", "WARNING", name, message=f"Review necessity and distribution suitability: {key}")
    ctx.inventories["signing"] = {"sourceEntitlements": entitlements, "staticRequiresSigning": False,
        "distribution": ctx.config.get("distribution", "sideload-unsigned"),
        "observedCapabilities": [key for key in entitlements if any(x in key for x in ("aps", "keychain", "application-groups", "icloud", "associated-domains"))]}
    ctx.review("signing-policy", "Review bundle/team/provisioning ownership and capability requirements for the selected distribution; static checks do not require signing.")
