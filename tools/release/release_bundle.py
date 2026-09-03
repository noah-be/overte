#!/usr/bin/env python3
"""Fail-closed creation and validation for Overte Android release bundles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
from urllib.parse import urlparse
import zipfile


SCHEMA = "org.overte.release-bundle.v1"
PROVENANCE_TYPE = "https://slsa.dev/provenance/v1"
REQUIRED_CATEGORIES = {
    "asset", "conan", "font", "gradle", "native", "openssl", "qt",
    "script", "v8",
}
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
SPDX = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*(?: WITH [A-Za-z0-9.+-]+)?")
UNRESOLVED = re.compile(r"(?:^|[^A-Za-z0-9])(?:NOASSERTION|NONE|UNKNOWN)(?:$|[^A-Za-z0-9])")


class BundleError(RuntimeError):
    """A release bundle violated the common contract."""


def fail(message: str) -> None:
    raise BundleError(message)


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        fail(f"{label} must be a regular non-symlink file")
    return path


def load_object(path: Path, label: str) -> dict:
    regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"invalid {label}: {error}")
    if not isinstance(value, dict):
        fail(f"{label} must contain a JSON object")
    return value


def safe_name(value: object, label: str) -> str:
    if (not isinstance(value, str) or Path(value).name != value
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", value)):
        fail(f"{label} must be a non-empty basename")
    return value


def resolved_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        fail(f"{label} must be a non-empty normalized string")
    if UNRESOLVED.search(value.upper()):
        fail(f"{label} is unresolved")
    return value


def validated_inventory(value: dict) -> tuple[list[dict], set[str]]:
    if value.get("schema") != "org.overte.release-license-inventory.v1":
        fail("license inventory has the wrong schema")
    if value.get("complete") is not True:
        fail("license inventory must explicitly attest complete=true")
    components = value.get("components")
    if not isinstance(components, list) or not components:
        fail("license inventory must contain components")
    refs: set[str] = set()
    categories: set[str] = set()
    for index, component in enumerate(components):
        label = f"license component {index}"
        if not isinstance(component, dict):
            fail(f"{label} must be an object")
        bom_ref = component.get("bom_ref")
        if not isinstance(bom_ref, str) or not bom_ref or bom_ref in refs:
            fail(f"{label} has a missing or duplicate bom_ref")
        refs.add(bom_ref)
        for field in ("name", "version", "source", "spdx_license"):
            resolved_text(component.get(field), f"{label} {field}")
        if not isinstance(component.get("sha256"), str):
            fail(f"{label} is missing sha256")
        if not HEX64.fullmatch(component["sha256"]):
            fail(f"{label} has an invalid sha256")
        if not SPDX.fullmatch(component["spdx_license"]):
            fail(f"{label} has an invalid SPDX license expression")
        source = urlparse(component["source"])
        if source.scheme not in {"https", "http", "git+https"} or not source.netloc:
            fail(f"{label} source must be an absolute source URI")
        component_categories = component.get("categories")
        if not isinstance(component_categories, list) or not component_categories:
            fail(f"{label} must declare categories")
        if any(not isinstance(category, str) or not category for category in component_categories):
            fail(f"{label} has an invalid category")
        categories.update(component_categories)
        purl = component.get("purl")
        if "conan" in component_categories and (
                not isinstance(purl, str) or not purl.startswith("pkg:conan/")):
            fail(f"{label} must contain a Conan package URL")
        if "gradle" in component_categories and (
                not isinstance(purl, str) or not purl.startswith(("pkg:maven/", "pkg:gradle/"))):
            fail(f"{label} must contain a package URL")
        notices = component.get("notice_files")
        if not isinstance(notices, list) or not notices:
            fail(f"{label} must reference at least one shipped notice file")
        for notice in notices:
            safe_archive_path(notice, f"{label} notice")
    missing = REQUIRED_CATEGORIES - categories
    if missing:
        fail("license inventory is missing dependency categories: " + ", ".join(sorted(missing)))
    return components, refs


def safe_archive_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        fail(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        fail(f"{label} is not a safe relative path")
    return path


def validate_notice_archive(path: Path, components: list[dict]) -> None:
    regular_file(path, "NOTICE bundle")
    try:
        with zipfile.ZipFile(path) as archive:
            names: set[str] = set()
            total_size = 0
            for info in archive.infolist():
                name = str(safe_archive_path(info.filename, "NOTICE entry"))
                unix_type = (info.external_attr >> 16) & 0o170000
                if info.is_dir() or unix_type not in (0, 0o100000):
                    fail("NOTICE bundle must contain regular files only")
                total_size += info.file_size
                if info.file_size > 16 * 1024 * 1024 or total_size > 64 * 1024 * 1024:
                    fail("NOTICE bundle exceeds the contract size limit")
                if name in names or info.file_size == 0:
                    fail("NOTICE bundle contains a duplicate or empty file")
                archive.read(info)
                names.add(name)
    except (OSError, zipfile.BadZipFile) as error:
        fail(f"invalid NOTICE bundle: {error}")
    required = {"NOTICE.txt"}
    for component in components:
        required.update(component["notice_files"])
    missing = required - names
    if missing:
        fail("NOTICE bundle is missing referenced text: " + ", ".join(sorted(missing)))


def validate_source_archive(path: Path) -> None:
    regular_file(path, "source archive")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            members = archive.getmembers()
            if not members:
                fail("source archive is empty")
            for member in members:
                safe_archive_path(member.name, "source archive entry")
                if member.issym() or member.islnk() or member.isdev():
                    fail("source archive contains a link or device")
    except (OSError, tarfile.TarError) as error:
        fail(f"invalid source archive: {error}")


def validate_environment(value: dict, components: list[dict]) -> None:
    component_refs = {component["bom_ref"] for component in components}
    if value.get("schema") != "org.overte.release-build-environment.v1":
        fail("build environment has the wrong schema")
    for field in ("builder_id", "runner_image"):
        resolved_text(value.get(field), f"build environment {field}")
    toolchain = value.get("toolchain")
    if not isinstance(toolchain, dict) or not toolchain or any(
            not isinstance(key, str) or not isinstance(version, str) or not version.strip()
            for key, version in toolchain.items()):
        fail("build environment needs a complete versioned toolchain")
    actions = value.get("actions")
    if not isinstance(actions, list) or not actions or any(
            not isinstance(action, dict)
            or not isinstance(action.get("name"), str) or not action["name"].strip()
            or not HEX40.fullmatch(str(action.get("sha", "")))
            for action in actions):
        fail("build environment actions must be pinned to full SHAs")
    resolved = value.get("resolved_dependencies")
    if not isinstance(resolved, list):
        fail("build environment needs resolved dependency revisions")
    resolved_refs: set[str] = set()
    for dependency in resolved:
        if not isinstance(dependency, dict) or dependency.get("bom_ref") not in component_refs:
            fail("build environment contains an unknown dependency reference")
        for field in ("recipe_revision", "package_revision"):
            resolved_text(dependency.get(field), f"dependency {field}")
        resolved_refs.add(dependency["bom_ref"])
    missing = {
        component["bom_ref"] for component in components
        if "conan" in component["categories"]
    } - resolved_refs
    if missing:
        fail("build environment omits Conan recipe/package revisions")


def parse_checksums(path: Path) -> dict[str, str]:
    regular_file(path, "SHA256SUMS")
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\s]+)", line)
        if not match:
            fail("SHA256SUMS contains an invalid line")
        name = str(safe_archive_path(match.group(2), "checksum path"))
        if name in result:
            fail("SHA256SUMS contains a duplicate path")
        result[name] = match.group(1)
    if not result:
        fail("SHA256SUMS is empty")
    return result


def validate_bundle(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        fail("bundle must be a real directory")
    directory = directory.absolute()
    for path in directory.rglob("*"):
        if path.is_symlink():
            fail(f"bundle contains symlink: {path.relative_to(directory)}")
    contract = load_object(directory / "release-bundle.json", "release bundle manifest")
    if contract.get("schema") != SCHEMA:
        fail("release bundle has the wrong schema")
    if contract.get("complete") is not True:
        fail("release bundle must explicitly attest complete=true")
    if not isinstance(contract.get("product"), str) or not contract["product"]:
        fail("release bundle is missing product")
    if not HEX40.fullmatch(str(contract.get("source_revision", ""))):
        fail("release bundle has an invalid source revision")
    if not isinstance(contract.get("release_tag"), str) or not contract["release_tag"]:
        fail("release bundle is missing release tag")
    artifacts = contract.get("artifacts")
    required_roles = {
        "payload", "build_manifest", "sbom", "license_inventory", "notice_bundle",
        "provenance", "source_archive", "checksums",
    }
    if not isinstance(artifacts, dict) or set(artifacts) != required_roles:
        fail("release bundle artifact roles are incomplete or unexpected")
    paths: dict[str, Path] = {}
    for role, entry in artifacts.items():
        if not isinstance(entry, dict):
            fail(f"artifact {role} must be an object")
        name = safe_name(entry.get("path"), f"artifact {role} path")
        if not HEX64.fullmatch(str(entry.get("sha256", ""))):
            fail(f"artifact {role} has an invalid digest")
        path = regular_file(directory / name, f"artifact {role}")
        if sha256(path) != entry["sha256"]:
            fail(f"artifact {role} digest mismatch")
        paths[role] = path
    if len(set(paths.values())) != len(paths):
        fail("release bundle artifact paths must be unique")
    actual_names = {path.name for path in directory.iterdir() if path.is_file()}
    expected_names = {"release-bundle.json", *(path.name for path in paths.values())}
    nested = sorted(path.name for path in directory.iterdir() if path.is_dir())
    if actual_names != expected_names or nested:
        fail(
            "release bundle contains missing, nested, or unexpected files "
            f"(missing={sorted(expected_names - actual_names)}, "
            f"unexpected={sorted(actual_names - expected_names)}, nested={nested})"
        )

    inventory = load_object(paths["license_inventory"], "license inventory")
    components, refs = validated_inventory(inventory)
    validate_notice_archive(paths["notice_bundle"], components)
    validate_source_archive(paths["source_archive"])
    build = load_object(paths["build_manifest"], "build manifest")
    if build.get("schema") != "org.overte.release-build-manifest.v1":
        fail("build manifest has the wrong schema")
    if build.get("product") != contract["product"] or build.get("source_revision") != contract["source_revision"]:
        fail("build manifest identity disagrees with bundle")
    verified = build.get("verified_artifact")
    if not isinstance(verified, dict) or verified.get("source_revision") != contract["source_revision"] \
            or verified.get("sha256") != sha256(paths["payload"]):
        fail("verified artifact is not bound to the bundle payload")
    version = build.get("version")
    if not isinstance(version, dict) or version.get("source_revision") != contract["source_revision"]:
        fail("build version is not bound to the bundle source")
    for field in ("tag", "version_name", "version_code"):
        if field not in version or version[field] in (None, ""):
            fail(f"build version is missing {field}")
    if version["tag"] != contract["release_tag"]:
        fail("build version tag disagrees with bundle")
    validate_environment(build.get("environment", {}), components)

    sbom = load_object(paths["sbom"], "SBOM")
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        fail("SBOM must be CycloneDX 1.6")
    sbom_components = sbom.get("components")
    if (not isinstance(sbom_components, list) or len(sbom_components) != len(refs)
            or any(not isinstance(item, dict) for item in sbom_components)
            or len({item.get("bom-ref") for item in sbom_components}) != len(sbom_components)
            or {item.get("bom-ref") for item in sbom_components} != refs):
        fail("SBOM and license inventory component sets disagree")
    if sbom.get("metadata") != {"component": {
            "type": "application", "name": contract["product"],
            "version": str(version["version_name"]),
    }}:
        fail("SBOM application identity disagrees with bundle")
    inventory_by_ref = {component["bom_ref"]: component for component in components}
    for component in sbom_components:
        if not isinstance(component, dict):
            fail("SBOM component must be an object")
        expected = inventory_by_ref[component["bom-ref"]]
        if component.get("name") != expected["name"] or component.get("version") != expected["version"]:
            fail("SBOM component identity disagrees with license inventory")
        if component.get("purl") != expected.get("purl"):
            fail("SBOM component package URL disagrees with license inventory")
        if component.get("hashes") != [{"alg": "SHA-256", "content": expected["sha256"]}]:
            fail("SBOM component digest disagrees with license inventory")
        if component.get("licenses") != [{"expression": expected["spdx_license"]}]:
            fail("SBOM component license disagrees with license inventory")
        if component.get("externalReferences") != [{"type": "website", "url": expected["source"]}]:
            fail("SBOM component source disagrees with license inventory")
        expected_properties = [
            {"name": "org.overte.dependency-category", "value": category}
            for category in sorted(expected["categories"])
        ]
        if component.get("properties") != expected_properties:
            fail("SBOM dependency categories disagree with license inventory")

    checksums = parse_checksums(paths["checksums"])
    expected_checksum_roles = required_roles - {"checksums", "provenance"}
    expected_names = {paths[role].name for role in expected_checksum_roles}
    if set(checksums) != expected_names:
        fail("SHA256SUMS does not cover the exact non-cyclic artifact set")
    for name, digest in checksums.items():
        if sha256(regular_file(directory / name, "checksummed artifact")) != digest:
            fail(f"checksum mismatch for {name}")

    provenance = load_object(paths["provenance"], "provenance")
    if provenance.get("_type") != "https://in-toto.io/Statement/v1" or provenance.get("predicateType") != PROVENANCE_TYPE:
        fail("provenance must be an in-toto SLSA v1 statement")
    subjects = provenance.get("subject")
    expected_subjects = {
        paths[role].name: sha256(paths[role])
        for role in ("payload", "sbom", "license_inventory", "notice_bundle",
                     "source_archive", "checksums")
    }
    actual_subjects = {}
    if not isinstance(subjects, list) or len(subjects) != len(expected_subjects):
        fail("provenance subjects are incomplete or have mismatched digests")
    for subject in subjects:
        if (not isinstance(subject, dict) or set(subject) != {"name", "digest"}
                or not isinstance(subject["name"], str)
                or not isinstance(subject["digest"], dict)
                or set(subject["digest"]) != {"sha256"}
                or subject["name"] in actual_subjects):
            fail("provenance subjects are malformed or duplicated")
        actual_subjects[subject["name"]] = subject["digest"]["sha256"]
    if actual_subjects != expected_subjects:
        fail("provenance subjects are incomplete or have mismatched digests")
    expected_predicate = {
        "buildDefinition": {
            "buildType": f"https://overte.org/buildtypes/{contract['product']}-release/v1",
            "externalParameters": {"version": build["version"]},
            "resolvedDependencies": build["environment"]["resolved_dependencies"],
        },
        "runDetails": {
            "builder": {"id": build["environment"]["builder_id"]},
            "metadata": {
                "runnerImage": build["environment"]["runner_image"],
                "toolchain": build["environment"]["toolchain"],
                "actions": build["environment"]["actions"],
            },
        },
    }
    if provenance.get("predicate") != expected_predicate:
        fail("provenance predicate disagrees with the verified build manifest")
    return contract


def create_bundle(*, product: str, source_revision: str, payload: Path,
                  verified_manifest: Path, version_manifest: Path,
                  dependency_inventory: Path, notice_bundle: Path,
                  source_archive: Path, build_environment: Path,
                  output: Path) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", product):
        fail("product must be a lowercase portable identifier")
    if not HEX40.fullmatch(source_revision):
        fail("source revision must be a lowercase 40-character commit")
    inputs = {
        "payload": regular_file(payload.absolute(), "payload"),
        "verified_manifest": regular_file(verified_manifest.absolute(), "verified manifest"),
        "version_manifest": regular_file(version_manifest.absolute(), "version manifest"),
        "license_inventory": regular_file(dependency_inventory.absolute(), "license inventory"),
        "notice_bundle": regular_file(notice_bundle.absolute(), "NOTICE bundle"),
        "source_archive": regular_file(source_archive.absolute(), "source archive"),
        "build_environment": regular_file(build_environment.absolute(), "build environment"),
    }
    inventory = load_object(inputs["license_inventory"], "license inventory")
    components, refs = validated_inventory(inventory)
    validate_notice_archive(inputs["notice_bundle"], components)
    validate_source_archive(inputs["source_archive"])
    environment = load_object(inputs["build_environment"], "build environment")
    validate_environment(environment, components)
    verified = load_object(inputs["verified_manifest"], "verified manifest")
    version = load_object(inputs["version_manifest"], "version manifest")
    for manifest, label in ((verified, "verified manifest"), (version, "version manifest")):
        if manifest.get("source_revision") != source_revision:
            fail(f"{label} source revision disagrees with bundle")
    for field in ("tag", "version_name", "version_code"):
        if field not in version or version[field] in (None, ""):
            fail(f"version manifest is missing {field}")
    if verified.get("sha256") != sha256(inputs["payload"]):
        fail("payload digest disagrees with verified manifest")

    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        fail("bundle output must be a real directory path")
    if output.exists() and any(output.iterdir()):
        fail("bundle output directory must be empty")
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.release-bundle.", dir=output.parent))
    try:
        names = {
            "payload": payload.name,
            "build_manifest": f"{product}-release-manifest.json",
            "sbom": f"{product}-sbom.cdx.json",
            "license_inventory": f"{product}-licenses.json",
            "notice_bundle": f"{product}-license-notices.zip",
            "provenance": f"{product}-provenance.intoto.json",
            "source_archive": f"{product}-source.tar",
            "checksums": "SHA256SUMS",
        }
        if len(set(names.values())) != len(names):
            fail("payload basename collides with a reserved bundle filename")
        for role in ("payload", "notice_bundle", "source_archive"):
            shutil.copyfile(inputs[role], staging / names[role], follow_symlinks=False)
        (staging / names["license_inventory"]).write_text(canonical_json(inventory), encoding="utf-8")
        sbom_components = []
        for component in sorted(components, key=lambda item: item["bom_ref"]):
            entry = {
                "type": "library", "bom-ref": component["bom_ref"],
                "name": component["name"], "version": component["version"],
                "hashes": [{"alg": "SHA-256", "content": component["sha256"]}],
                "licenses": [{"expression": component["spdx_license"]}],
                "externalReferences": [{"type": "website", "url": component["source"]}],
                "properties": [{"name": "org.overte.dependency-category", "value": category}
                               for category in sorted(component["categories"])],
            }
            if component.get("purl"):
                entry["purl"] = component["purl"]
            sbom_components.append(entry)
        sbom = {
            "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"component": {"type": "application", "name": product,
                                         "version": str(version.get("version_name", ""))}},
            "components": sbom_components,
        }
        (staging / names["sbom"]).write_text(canonical_json(sbom), encoding="utf-8")
        build = {
            "schema": "org.overte.release-build-manifest.v1", "product": product,
            "source_revision": source_revision, "verified_artifact": verified,
            "version": version, "environment": environment,
        }
        (staging / names["build_manifest"]).write_text(canonical_json(build), encoding="utf-8")
        checksum_roles = ("payload", "build_manifest", "sbom", "license_inventory",
                          "notice_bundle", "source_archive")
        (staging / names["checksums"]).write_text(
            "".join(f"{sha256(staging / names[role])}  {names[role]}\n"
                    for role in sorted(checksum_roles, key=lambda item: names[item])),
            encoding="utf-8",
        )
        provenance_subject_roles = ("payload", "sbom", "license_inventory", "notice_bundle",
                                    "source_archive", "checksums")
        provenance = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [{"name": names[role], "digest": {"sha256": sha256(staging / names[role])}}
                        for role in provenance_subject_roles],
            "predicateType": PROVENANCE_TYPE,
            "predicate": {
                "buildDefinition": {
                    "buildType": f"https://overte.org/buildtypes/{product}-release/v1",
                    "externalParameters": {"version": version},
                    "resolvedDependencies": environment["resolved_dependencies"],
                },
                "runDetails": {"builder": {"id": environment["builder_id"]},
                               "metadata": {"runnerImage": environment["runner_image"],
                                            "toolchain": environment["toolchain"],
                                            "actions": environment["actions"]}},
            },
        }
        (staging / names["provenance"]).write_text(canonical_json(provenance), encoding="utf-8")
        artifacts = {
            role: {"path": name, "sha256": sha256(staging / name)}
            for role, name in names.items()
        }
        contract = {"schema": SCHEMA, "complete": True, "product": product,
                    "source_revision": source_revision, "release_tag": version["tag"],
                    "artifacts": artifacts}
        (staging / "release-bundle.json").write_text(canonical_json(contract), encoding="utf-8")
        validate_bundle(staging)
        if output.exists():
            output.rmdir()
        os.replace(staging, output)
        validate_bundle(output)
        return contract
    finally:
        shutil.rmtree(staging, ignore_errors=True)
