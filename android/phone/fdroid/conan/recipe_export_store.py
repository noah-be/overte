#!/usr/bin/env python3
"""Validate directory recipe exports and restore them into an attempt cache."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath


class RecipeStoreError(RuntimeError):
    pass


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path):
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecipeStoreError(f"duplicate key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def validate(index_path: Path):
    index = load_json(index_path)
    if index.get("schema_version") != 1 or len(index.get("recipes", {})) != 51:
        raise RecipeStoreError("recipe index schema/count mismatch")
    root = index_path.parent
    pkglist = load_json(root / "pkglist.json")
    if set(pkglist) != set(index["recipes"]):
        raise RecipeStoreError("pkglist/index reference mismatch")
    cache_folders = set()
    forbidden_suffixes = (".a", ".aar", ".apk", ".class", ".dex", ".dll", ".exe", ".jar", ".o", ".so")
    for reference, entry in index["recipes"].items():
        if not entry.get("rrev") or len(entry["rrev"]) != 32:
            raise RecipeStoreError(f"invalid RREV: {reference}")
        cache_folder = entry.get("cache_folder")
        if not cache_folder or cache_folder in cache_folders or "/" in cache_folder:
            raise RecipeStoreError(f"invalid cache folder: {reference}")
        cache_folders.add(cache_folder)
        pkgmeta = pkglist[reference].get("revisions", {}).get(entry["rrev"])
        if not pkgmeta or pkgmeta["recipe_folder"] != cache_folder:
            raise RecipeStoreError(f"pkglist revision mismatch: {reference}")
        actual = {}
        ref_root = root / reference
        for path in sorted(ref_root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(ref_root).as_posix()
                if path.name.lower().endswith(forbidden_suffixes):
                    raise RecipeStoreError(f"binary in recipe store: {reference}:{relative}")
                if "p" in PurePosixPath(relative).parts or "s" in PurePosixPath(relative).parts:
                    raise RecipeStoreError(f"package/source cache path in recipe store: {reference}:{relative}")
                actual[relative] = sha256_file(path)
        if actual != entry.get("files"):
            raise RecipeStoreError(f"recipe file ledger mismatch: {reference}")
        if "export/conanfile.py" not in actual or "export/conanmanifest.txt" not in actual:
            raise RecipeStoreError(f"incomplete recipe export: {reference}")
        # The ledger alone cannot prove completeness: both it and the directory
        # previously omitted three patches required by frozen Conan manifests.
        lines = (ref_root / "export/conanmanifest.txt").read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].isdigit():
            raise RecipeStoreError(f"invalid Conan export manifest: {reference}")
        declared = {}
        for line in lines[1:]:
            parts = line.rsplit(": ", 1)
            if len(parts) != 2:
                raise RecipeStoreError(f"invalid Conan export manifest entry: {reference}")
            name, expected_md5 = parts
            if (not name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                    or len(expected_md5) != 32 or any(c not in "0123456789abcdef" for c in expected_md5)):
                raise RecipeStoreError(f"invalid Conan export manifest path/hash: {reference}")
            relative = ("export_sources/" + name.removeprefix("export_source/")) if name.startswith("export_source/") else "export/" + name
            if relative in declared:
                raise RecipeStoreError(f"duplicate Conan export manifest path: {reference}")
            declared[relative] = expected_md5
        if set(declared) != set(actual) - {"export/conanmanifest.txt"}:
            raise RecipeStoreError(f"Conan export manifest file set mismatch: {reference}")
        for relative, expected_md5 in declared.items():
            # MD5 is Conan's legacy manifest format, not our security digest;
            # the independently bound index also validates every file's SHA256.
            if hashlib.md5((ref_root / relative).read_bytes(), usedforsecurity=False).hexdigest() != expected_md5:
                raise RecipeStoreError(f"Conan export manifest byte mismatch: {reference}:{relative}")
    return index, pkglist


def _add_directory(archive, name):
    info = tarfile.TarInfo(name.rstrip("/") + "/")
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.mtime = 3600
    info.uid = info.gid = 0
    archive.addfile(info)


def _add_bytes(archive, name, data, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = 3600
    info.uid = info.gid = 0
    archive.addfile(info, io.BytesIO(data))


def create_transport(index_path: Path, output: Path, scanned_root: Path):
    index, pkglist = validate(index_path)
    output = output.resolve()
    scanned_root = scanned_root.resolve()
    if output == scanned_root or scanned_root in output.parents:
        raise RecipeStoreError("transport archive must be outside scanned source tree")
    if output.exists():
        raise RecipeStoreError("stale transport archive already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".new")
    root = index_path.parent
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for reference, entry in sorted(index["recipes"].items(), key=lambda item: item[1]["cache_folder"]):
                    folder = entry["cache_folder"]
                    for directory in (folder, f"{folder}/d", f"{folder}/d/metadata", f"{folder}/e"):
                        _add_directory(archive, directory)
                    # Conan requires es/ whenever export_sources() exists, even
                    # if a recipe version exports zero files.
                    # Git cannot preserve empty directories. Include this empty
                    # cache-layout directory for every validated recipe; it adds
                    # no source/package bytes and leaves every RREV unchanged.
                    _add_directory(archive, f"{folder}/es")
                    seen_dirs = {folder, f"{folder}/d", f"{folder}/d/metadata", f"{folder}/e", f"{folder}/es"}
                    for relative in sorted(entry["files"]):
                        if relative.startswith("export/"):
                            member = f"{folder}/e/{relative.removeprefix('export/')}"
                        elif relative.startswith("export_sources/"):
                            member = f"{folder}/es/{relative.removeprefix('export_sources/')}"
                        else:
                            raise RecipeStoreError(f"unexpected recipe path: {reference}:{relative}")
                        parent = PurePosixPath(member).parent
                        parents = []
                        while parent.as_posix() not in seen_dirs and parent.as_posix() != ".":
                            parents.append(parent.as_posix())
                            parent = parent.parent
                        for directory in reversed(parents):
                            _add_directory(archive, directory)
                            seen_dirs.add(directory)
                        source_path = root / reference / relative
                        _add_bytes(archive, member, source_path.read_bytes(), source_path.stat().st_mode & 0o777)
                pkgdata = json.dumps(pkglist, separators=(",", ":"), sort_keys=False).encode("utf-8")
                _add_bytes(archive, "pkglist.json", pkgdata)
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temporary, output)
    return sha256_file(output)


def _conan_json(home: Path, *args):
    env = {**os.environ, "CONAN_HOME": str(home)}
    result = subprocess.run(["conan", *args, "--format=json"], env=env, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def restore(index_path: Path, conan_home: Path, transport: Path, scanned_root: Path):
    conan_home = conan_home.resolve()
    if not conan_home.is_absolute() or conan_home == Path.home() / ".conan2":
        raise RecipeStoreError("attempt-local CONAN_HOME is required")
    conan_home.mkdir(parents=True, exist_ok=True)
    remotes = _conan_json(conan_home, "remote", "list")
    if remotes:
        raise RecipeStoreError("Conan remotes must be removed before recipe restore")
    listing = _conan_json(conan_home, "list", "*#*")
    if listing.get("Local Cache"):
        raise RecipeStoreError("Conan cache is not empty before recipe restore")
    create_transport(index_path, transport, scanned_root)
    env = {**os.environ, "CONAN_HOME": str(conan_home)}
    subprocess.run(["conan", "cache", "restore", str(transport)], env=env, check=True)
    restored = _conan_json(conan_home, "list", "*#*").get("Local Cache", {})
    index, _ = validate(index_path)
    if set(restored) != set(index["recipes"]):
        raise RecipeStoreError("restored recipe reference set mismatch")
    for reference, entry in index["recipes"].items():
        revisions = restored[reference].get("revisions", {})
        if set(revisions) != {entry["rrev"]}:
            raise RecipeStoreError(f"restored RREV mismatch: {reference}")
        export_sources = conan_home / "p" / entry["cache_folder"] / "es"
        if not export_sources.is_dir() or export_sources.is_symlink():
            raise RecipeStoreError(f"restored export-sources directory missing: {reference}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "create-transport", "restore"))
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--scanned-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--conan-home", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        index, _ = validate(args.index.resolve())
        print(f"recipe export store PASS: {len(index['recipes'])} recipes")
    elif args.command == "create-transport":
        if not args.output:
            parser.error("create-transport requires --output")
        print(create_transport(args.index.resolve(), args.output, args.scanned_root))
    else:
        if not args.output or not args.conan_home:
            parser.error("restore requires --output and --conan-home")
        restore(args.index.resolve(), args.conan_home, args.output, args.scanned_root)
        print("attempt-local recipe restore PASS")


if __name__ == "__main__":
    try:
        main()
    except (RecipeStoreError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"recipe-export-store: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
