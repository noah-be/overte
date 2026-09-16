#!/usr/bin/env python3
"""Publish immutable QML/client-JS revisions over House Arrest (no IPA/build).

Uses pymobiledevice3's async API. A local Documents backend exercises the same
publisher without a device. Device identity lives in a private profile, not CLI
arguments/logs. No automatic app termination, signing, installation or cleanup.
"""
import argparse
import asyncio
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import uuid

BASE = "OverteDevelopment"
HASH = re.compile(r"[a-f0-9]{64}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def safe(path):
    return (isinstance(path, str) and path and not path.startswith("/") and
            not any(x in path for x in ("\\", ":")) and
            all(x not in ("", ".", "..") for x in path.split("/")))


def pack(repo, output, resources=(), scripts=True):
    """Always include the complete script tree, preserving include/require bases."""
    files = {}
    sources = [(repo / "interface/resources/qml", "resources/qml")]
    if scripts:
        sources.append((repo / "scripts", "scripts"))
    for resource in resources:
        if not safe(resource):
            raise ValueError("invalid resource path")
        sources.append((repo / "interface/resources" / resource, "resources/" + resource))
    content = {}
    for source, prefix in sources:
        if not source.exists():
            raise ValueError("missing source input")
        paths = sorted(source.rglob("*")) if source.is_dir() else [source]
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(repo.resolve()):
                raise ValueError("source symlink or containment failure")
            if not path.is_file():
                continue
            name = prefix + "/" + path.relative_to(source).as_posix() if source.is_dir() else prefix
            data = path.read_bytes()
            files[name] = digest(data)
            content[name] = data
    if scripts and "scripts/defaultScripts.js" not in files:
        raise ValueError("missing defaultScripts.js")
    import subprocess
    source_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    manifest = encode({"schema": 1, "source": source_sha, "scripts": scripts, "files": files})
    revision = digest(manifest)
    destination = output / revision
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise ValueError("existing immutable revision differs")
        if not path.exists():
            path.write_bytes(data)
    manifest_path = destination / "manifest.json"
    if manifest_path.exists() and manifest_path.read_bytes() != manifest:
        raise ValueError("existing immutable manifest differs")
    if not manifest_path.exists():
        manifest_path.write_bytes(manifest)
    return {"revision": revision, "files": len(files), "bytes": sum(map(len, content.values()))}


class LocalDocuments:
    def __init__(self, root):
        self.root = root.resolve()

    def path(self, name):
        if not safe(name):
            raise ValueError("invalid transport path")
        result = self.root / name
        if not result.resolve().is_relative_to(self.root):
            raise ValueError("transport containment failure")
        return result

    async def read(self, name):
        path = self.path(name)
        return path.read_bytes() if path.exists() else None

    async def write(self, name, data):
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def rename(self, old, new):
        self.path(old).replace(self.path(new))


class DeviceDocuments:
    def __init__(self, house):
        self.house = house

    def path(self, name):
        if not safe(name):
            raise ValueError("invalid transport path")
        return "/Documents/" + name

    async def read(self, name):
        path = self.path(name)
        return await self.house.get_file_contents(path) if await self.house.exists(path) else None

    async def write(self, name, data):
        path = self.path(name)
        await self.house.makedirs(str(PurePosixPath(path).parent))
        await self.house.set_file_contents(path, data)

    async def rename(self, old, new):
        await self.house.rename(self.path(old), self.path(new))


async def atomic_json(transport, name, value):
    temporary = name + "." + uuid.uuid4().hex + ".pending"
    data = encode(value)
    await transport.write(temporary, data)
    if await transport.read(temporary) != data:
        raise ValueError("request readback failed")
    # AFC rename is the only activation boundary. On failure keep the existing
    # request and staged data; never implement replacement by deleting it first.
    await transport.rename(temporary, name)


async def capability(transport):
    data = await transport.read(BASE + "/capabilities.json")
    cap = json.loads(data or b"{}")
    if cap.get("schema") != 1 or cap.get("apply") != "restart" or not HASH.fullmatch(cap.get("installation", "")):
        raise ValueError("compatible E2E foundation must be installed and launched once")
    return cap


async def activate(transport, revision):
    if not HASH.fullmatch(revision):
        raise ValueError("invalid revision")
    cap = await capability(transport)
    manifest = await transport.read(BASE + "/revisions/" + revision + "/manifest.json")
    if not manifest or digest(manifest) != revision:
        raise ValueError("revision has not been completely published")
    await atomic_json(transport, BASE + "/active.json", {
        "schema": 1, "installation": cap["installation"], "revision": revision})
    return {"state": "restart-required", "revision": revision}


async def push(transport, directory):
    await capability(transport)  # Fail before transferring incompatible content.
    manifest_bytes = (directory / "manifest.json").read_bytes()
    revision = digest(manifest_bytes)
    manifest = json.loads(manifest_bytes)
    files = manifest.get("files", {})
    if manifest.get("schema") != 1 or not files:
        raise ValueError("invalid manifest")
    # Validate every input before any writes. Never follow a path outside pack.
    for name, sha in files.items():
        path = directory / name
        if (not safe(name) or not name.startswith(("scripts/", "resources/")) or
                path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or
                digest(path.read_bytes()) != sha):
            raise ValueError("invalid package member")
    prefix = BASE + "/revisions/" + revision + "/"
    sealed = await transport.read(prefix + "manifest.json")
    if sealed is not None and sealed != manifest_bytes:
        raise ValueError("immutable remote revision conflict")
    uploaded = 0
    for name, sha in files.items():
        present = await transport.read(prefix + name)
        if present is not None and digest(present) == sha:
            continue
        if sealed is not None:
            raise ValueError("sealed remote revision is corrupt; retained for inspection")
        await transport.write(prefix + name, (directory / name).read_bytes())
        if digest(await transport.read(prefix + name) or b"") != sha:
            raise ValueError("file transfer readback failed")
        uploaded += 1
    await transport.write(prefix + "manifest.json", manifest_bytes)
    if await transport.read(prefix + "manifest.json") != manifest_bytes:
        raise ValueError("manifest readback failed")
    result = await activate(transport, revision)
    return dict(result, uploaded=uploaded, reused=len(files) - uploaded)


async def command(transport, args):
    if args.command == "push":
        return await push(transport, args.package)
    if args.command == "activate":
        return await activate(transport, args.revision)
    if args.command == "disable":
        await capability(transport)
        # An absent revision is an explicit bundled selection, handled at start.
        await atomic_json(transport, BASE + "/active.json", {"schema": 1, "disabled": True})
        return {"state": "restart-required", "selection": "bundled"}
    return {name: json.loads(await transport.read(BASE + "/" + name + ".json") or b"null")
            for name in ("capabilities", "active", "status")}


async def run(args):
    if args.documents:
        return await command(LocalDocuments(args.documents), args)
    if not args.profile:
        raise ValueError("choose --profile or --documents")
    profile = json.loads(args.profile.read_text())
    # User's existing install/device-test locks can be listed in the private
    # profile. Hold them for the entire transaction, including readback.
    import fcntl
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.house_arrest import HouseArrestService
    with contextlib.ExitStack() as stack:
        locks = profile.get("locks", [])
        if not locks:
            raise ValueError("private device profile must specify coordination locks")
        for lock in sorted(set(locks)):
            file = stack.enter_context(open(Path(lock).expanduser(), "a"))
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lockdown = await create_using_usbmux(serial=profile["udid"], autopair=False)
        async with lockdown:
            async with await HouseArrestService.create(lockdown, profile["bundle_id"]) as house:
                return await command(DeviceDocuments(house), args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument("--documents", type=Path, help="local Documents backend (host tests/simulator container)")
    backend.add_argument("--profile", type=Path, help="private udid, bundle_id, locks JSON; never committed")
    parser.add_argument("--timeout", type=int, default=120)
    sub = parser.add_subparsers(dest="command", required=True)
    pack_args = sub.add_parser("pack")
    pack_args.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    pack_args.add_argument("--output", type=Path, required=True)
    pack_args.add_argument("--resource", action="append", default=[])
    pack_args.add_argument("--qml-only", action="store_true")
    sub.add_parser("push").add_argument("package", type=Path)
    sub.add_parser("activate").add_argument("revision")
    sub.add_parser("disable")
    sub.add_parser("status")
    args = parser.parse_args()
    try:
        result = (pack(args.repo, args.output, args.resource, not args.qml_only) if args.command == "pack"
                  else asyncio.run(asyncio.wait_for(run(args), args.timeout)))
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        # Transport exceptions can contain private selectors. Print an error
        # class plus our own bounded messages, never arbitrary device replies.
        message = str(error) if isinstance(error, ValueError) and error.__class__ is ValueError else "operation failed; staged data retained"
        print(json.dumps({"state": "error", "type": type(error).__name__, "reason": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
