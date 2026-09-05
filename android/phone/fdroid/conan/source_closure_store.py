#!/usr/bin/env python3
"""Acquire and verify the complete SH-001 source closure.

The online phase is the only code path which opens URLs.  The verify and
stage-conan-cache phases are deliberately local-only and are suitable for the
network-isolated build unit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


class ClosureError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ClosureError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _lock_refs(lock_path: Path):
    lock = load_json(lock_path)
    result = []
    for role in ("requires", "build_requires", "python_requires", "config_requires"):
        for value in lock.get(role, []):
            frozen = value.split("%", 1)[0]
            reference, revision = frozen.rsplit("#", 1)
            result.append((reference, revision, role))
    return result


def validate_manifest(manifest_path: Path, repo_root: Path):
    document = load_json(manifest_path)
    if document.get("schema_version") != 1:
        raise ClosureError("unsupported source-closure schema")
    recipe_index = document.get("recipe_export_index", {})
    for name in ("path", "sha256", "pkglist_path", "pkglist_sha256"):
        if not recipe_index.get(name):
            raise ClosureError(f"recipe export binding missing: {name}")
    for path_name, digest_name in (
        ("path", "sha256"), ("pkglist_path", "pkglist_sha256")
    ):
        bound_path = repo_root / recipe_index[path_name]
        if not bound_path.is_file() or sha256_file(bound_path) != recipe_index[digest_name]:
            raise ClosureError(f"recipe export binding mismatch: {path_name}")

    toolchain = document.get("toolchain_binding", {})
    toolchain_path = repo_root / toolchain.get("path", "")
    if not toolchain_path.is_file() or sha256_file(toolchain_path) != toolchain.get("sha256"):
        raise ClosureError("base toolchain binding mismatch")
    graph_refs = {}
    for graph_name, graph in document.get("graphs", {}).items():
        lock_path = repo_root / graph["path"]
        if sha256_file(lock_path) != graph["sha256"]:
            raise ClosureError(f"lock digest mismatch: {graph_name}")
        for reference, revision, role in _lock_refs(lock_path):
            graph_refs.setdefault((reference, revision), set()).add((graph_name, role))

    nodes = document.get("nodes", [])
    manifest_refs = {}
    for node in nodes:
        key = (node.get("reference"), node.get("recipe_revision"))
        if None in key or key in manifest_refs:
            raise ClosureError(f"missing or duplicate node identity: {key}")
        manifest_refs[key] = node
        declared = {(entry["graph"], entry["role"]) for entry in node["contexts"]}
        if declared != graph_refs.get(key, set()):
            raise ClosureError(f"context/host-target lineage mismatch: {key[0]}")
        classification = node.get("classification")
        if classification not in {"source-bearing", "virtual-system"}:
            raise ClosureError(f"invalid classification: {key[0]}")
        recipe = node.get("recipe", {})
        recipe_path = repo_root / recipe.get("path", "")
        if not recipe_path.is_file() or sha256_file(recipe_path) != recipe.get("sha256"):
            raise ClosureError(f"recipe identity mismatch: {key[0]}")
        for relative, expected in recipe.get("exported_files", {}).items():
            path = repo_root / relative
            if not path.is_file() or sha256_file(path) != expected:
                raise ClosureError(f"recipe export file mismatch: {key[0]}:{relative}")
        if classification == "virtual-system":
            if node.get("sources"):
                raise ClosureError(f"virtual node has downloaded sources: {key[0]}")
            if not node.get("system_binding", {}).get("toolchain_sha256"):
                raise ClosureError(f"virtual node lacks toolchain binding: {key[0]}")
            continue
        sources = node.get("sources", [])
        if not sources:
            raise ClosureError(f"source-bearing node has no sources: {key[0]}")
        for source in sources:
            _validate_source(source, key[0])

    if set(manifest_refs) != set(graph_refs):
        missing = sorted(set(graph_refs) - set(manifest_refs))
        extra = sorted(set(manifest_refs) - set(graph_refs))
        raise ClosureError(f"graph/manifest node mismatch; missing={missing}; extra={extra}")
    if len(nodes) != document.get("node_count"):
        raise ClosureError("node_count does not match manifest")
    return document


def _validate_source(source, reference):
    required = (
        "id",
        "retrieval",
        "canonical_url",
        "immutable_ref",
        "sha256",
        "max_bytes",
        "archive_format",
        "strip_components",
        "store_path",
        "approved_redirect_hosts",
        "license",
        "redistribution",
        "fdroid_exception",
    )
    missing = [name for name in required if name not in source]
    if missing:
        raise ClosureError(f"source fields missing for {reference}: {missing}")
    if source["retrieval"] != "https-archive":
        raise ClosureError(f"unsupported retrieval method for {reference}")
    parsed = urllib.parse.urlparse(source["canonical_url"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise ClosureError(f"non-public-HTTPS source for {reference}")
    if parsed.hostname not in source["approved_redirect_hosts"]:
        raise ClosureError(f"origin host absent from allowlist for {reference}")
    if len(source["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in source["sha256"]):
        raise ClosureError(f"bad archive digest for {reference}")
    if source["store_path"] != f"objects/sha256/{source['sha256'][:2]}/{source['sha256']}":
        raise ClosureError(f"non-content-addressed destination for {reference}")
    if not source["immutable_ref"] or source["immutable_ref"].lower() in {
        "main", "master", "head", "latest", "tip",
    }:
        raise ClosureError(f"mutable source ref for {reference}")
    license_data = source["license"]
    for name in ("spdx", "public_source", "path", "sha256"):
        if not license_data.get(name):
            raise ClosureError(f"license {name} missing for {reference}:{source['id']}")
    if len(license_data["sha256"]) != 64:
        raise ClosureError(f"bad license digest for {reference}:{source['id']}")


class _AllowlistedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = set(allowed_hosts)
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlparse(newurl).hostname
        if not _host_allowed(host, self.allowed_hosts):
            raise ClosureError(f"redirect target is not approved: {host}")
        self.chain.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _host_allowed(host, allowed_hosts):
    if not host:
        return False
    return host in allowed_hosts or any(
        entry.startswith(".") and host.endswith(entry) for entry in allowed_hosts
    )


def _download(source, partial: Path):
    if partial.is_file() and sha256_file(partial) == source["sha256"]:
        return []
    redirect = _AllowlistedRedirect(source["approved_redirect_hosts"])
    opener = urllib.request.build_opener(
        redirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "Overte-SH001-source-closure/1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(source["canonical_url"], headers=headers)
    response = None
    for attempt in range(5):
        try:
            response = opener.open(request, timeout=120)
            break
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 4:
                raise
            time.sleep(2 ** attempt)
        except urllib.error.URLError:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    if response is None:
        raise ClosureError(f"download retries exhausted: {source['id']}")
    mode = "ab" if existing and response.status == 206 else "wb"
    size = existing if mode == "ab" else 0
    with partial.open(mode) as output:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > source["max_bytes"]:
                raise ClosureError(f"source exceeds size limit: {source['id']}")
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    return redirect.chain


def _logical_member(name: str, strip_components: int):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ClosureError(f"unsafe archive path: {name}")
    parts = path.parts[strip_components:]
    return PurePosixPath(*parts).as_posix() if parts else ""


def _license_bytes(archive: Path, source):
    wanted = source["license"]["path"]
    strip = source["strip_components"]
    if source["archive_format"] in {"tar.gz", "tar.xz", "tar.bz2", "tar"}:
        with tarfile.open(archive, "r:*") as container:
            matches = [m for m in container.getmembers() if m.isfile() and _logical_member(m.name, strip) == wanted]
            if len(matches) != 1:
                raise ClosureError(f"license path count {len(matches)} for {source['id']}:{wanted}")
            handle = container.extractfile(matches[0])
            if handle is None:
                raise ClosureError(f"cannot read license for {source['id']}")
            return handle.read()
    if source["archive_format"] == "zip":
        with zipfile.ZipFile(archive) as container:
            matches = [n for n in container.namelist() if not n.endswith("/") and _logical_member(n, strip) == wanted]
            if len(matches) != 1:
                raise ClosureError(f"license path count {len(matches)} for {source['id']}:{wanted}")
            return container.read(matches[0])
    raise ClosureError(f"unsupported archive format: {source['archive_format']}")


def _source_entries(document):
    for node in document["nodes"]:
        for source in node.get("sources", []):
            yield node, source


def acquire(document, store: Path):
    staging = store / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    records = []
    for node, source in _source_entries(document):
        final = store / source["store_path"]
        complete = final / "COMPLETE.json"
        if complete.is_file():
            _verify_one(final / "source", source)
            state = "REUSED_VERIFIED"
            redirects = []
        else:
            partial = staging / f"{source['sha256']}.part"
            redirects = _download(source, partial)
            _verify_one(partial, source)
            candidate = Path(tempfile.mkdtemp(prefix=f"{source['sha256']}.", dir=staging))
            shutil.move(partial, candidate / "source")
            marker = {
                "schema_version": 1,
                "reference": node["reference"],
                "source_id": source["id"],
                "sha256": source["sha256"],
                "license_sha256": source["license"]["sha256"],
            }
            (candidate / "COMPLETE.json").write_text(
                json.dumps(marker, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            final.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.rename(candidate, final)
            except FileExistsError:
                _verify_one(final / "source", source)
            state = "ACQUIRED_VERIFIED"
        records.append({
            "reference": node["reference"], "source_id": source["id"],
            "sha256": source["sha256"], "store_path": source["store_path"],
            "license_path": source["license"]["path"],
            "license_sha256": source["license"]["sha256"], "state": state,
            "redirects": redirects,
        })
    _write_ledger(store, records)
    return records


def _verify_one(path: Path, source):
    if not path.is_file():
        raise ClosureError(f"missing source object: {source['id']}")
    if path.stat().st_size > source["max_bytes"]:
        raise ClosureError(f"stored source exceeds size limit: {source['id']}")
    if sha256_file(path) != source["sha256"]:
        raise ClosureError(f"source digest mismatch: {source['id']}")
    actual_license = hashlib.sha256(_license_bytes(path, source)).hexdigest()
    if actual_license != source["license"]["sha256"]:
        raise ClosureError(f"license digest mismatch: {source['id']}")


def verify(document, store: Path):
    records = []
    for node, source in _source_entries(document):
        final = store / source["store_path"]
        if not (final / "COMPLETE.json").is_file():
            raise ClosureError(f"incomplete source object: {node['reference']}:{source['id']}")
        _verify_one(final / "source", source)
        records.append((node["reference"], source["id"], source["sha256"]))
    if len(records) != sum(len(n.get("sources", [])) for n in document["nodes"]):
        raise ClosureError("offline store completeness mismatch")
    return records


def _write_ledger(store: Path, records):
    ledger = {"schema_version": 1, "objects": sorted(records, key=lambda r: (r["reference"], r["source_id"]))}
    temp = store / ".staging" / "CHECKSUM_LEDGER.json.new"
    temp.write_text(json.dumps(ledger, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, store / "CHECKSUM_LEDGER.json")


def stage_conan_cache(document, store: Path, destination: Path):
    verify(document, store)
    if destination.exists() and any(destination.iterdir()):
        raise ClosureError("destination Conan source cache is not empty")
    source_dir = destination / "s"
    source_dir.mkdir(parents=True, exist_ok=True)
    for node, source in _source_entries(document):
        target = source_dir / source["sha256"]
        shutil.copy2(store / source["store_path"] / "source", target)
        metadata = {
            "references": {node["reference"]: [source["canonical_url"]]},
            "source_closure_sha256": sha256_file(store / source["store_path"] / "source"),
        }
        (source_dir / f"{source['sha256']}.json").write_text(
            json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
        )


def stage_qt_store(document, store: Path, destination: Path):
    """Materialize the legacy Qt composer input view from the general store."""
    verify(document, store)
    if destination.exists() and any(destination.iterdir()):
        raise ClosureError("destination Qt source view is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    qt_nodes = [node for node in document["nodes"] if node["reference"].startswith("qt/")]
    if len(qt_nodes) != 1 or len(qt_nodes[0].get("sources", [])) != 17:
        raise ClosureError("exactly one 17-component Qt source node is required")
    for source in qt_nodes[0]["sources"]:
        target = destination / f"{source['sha256']}.tar.gz"
        shutil.copy2(store / source["store_path"] / "source", target)


def probe_licenses(document, staging: Path):
    """Online, non-committing helper used only to establish initial license locks."""
    staging.mkdir(parents=True, exist_ok=True)
    result = []
    for node, source in _source_entries(document):
        partial = staging / f"{source['sha256']}.part"
        _download(source, partial)
        if sha256_file(partial) != source["sha256"]:
            raise ClosureError(f"source digest mismatch while probing: {source['id']}")
        license_bytes = _license_bytes(partial, source)
        result.append({
            "reference": node["reference"], "source_id": source["id"],
            "license_path": source["license"]["path"],
            "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
        })
    print(json.dumps(result, sort_keys=True, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit-manifest", "acquire", "verify", "stage-conan-cache", "stage-qt-store", "probe-licenses"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    document = validate_manifest(args.manifest.resolve(), args.repo_root.resolve())
    if args.command == "audit-manifest":
        print(f"SOURCE_CLOSURE manifest PASS: {document['node_count']} nodes")
    elif args.command == "probe-licenses":
        if not args.store:
            parser.error("probe-licenses requires --store staging directory")
        probe_licenses(document, args.store.resolve())
    else:
        if not args.store:
            parser.error(f"{args.command} requires --store")
        if args.command == "acquire":
            print(json.dumps(acquire(document, args.store.resolve()), indent=2))
        elif args.command == "verify":
            print(f"offline source store PASS: {len(verify(document, args.store.resolve()))} objects")
        elif args.command == "stage-conan-cache":
            if not args.destination:
                parser.error("stage-conan-cache requires --destination")
            stage_conan_cache(document, args.store.resolve(), args.destination.resolve())
            print("Conan source cache staging PASS")
        elif args.command == "stage-qt-store":
            if not args.destination:
                parser.error("stage-qt-store requires --destination")
            stage_qt_store(document, args.store.resolve(), args.destination.resolve())
            print("Qt source view staging PASS")


if __name__ == "__main__":
    try:
        main()
    except (ClosureError, OSError, urllib.error.URLError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"source-closure: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
