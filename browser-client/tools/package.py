# SPDX-License-Identifier: Apache-2.0
"""Create a deterministic, auditable self-hosting archive from reviewed sources."""
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo)


def main():
    repo = Path(__file__).resolve().parents[2]
    scopes = ["browser-client", "docs/browser-client", "LICENSE", "LICENSES", "docs/LICENSING.md"]
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", *scopes)
    if untracked:
        raise SystemExit("Stage reviewed source files before packaging; untracked modules would be omitted.")
    files = {value for value in git(repo, "ls-files", "-z", "--", *scopes).decode().split("\0") if value}
    dist = repo / "browser-client/dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Run npm run build before packaging.")
    files.update(str(value.relative_to(repo)) for value in dist.rglob("*") if value.is_file())
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    mtime = int(git(repo, "show", "-s", "--format=%ct", "HEAD"))
    dirty = bool(git(repo, "status", "--porcelain", "--untracked-files=no", "--", *scopes).strip())
    version = json.loads((repo / "browser-client/package.json").read_bytes())["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise SystemExit("Invalid package version.")
    # Read each file once: manifest hashes and archive entries use the same bytes.
    # Never follow a distribution symlink into private operator/session files.
    snapshots = {}
    for name in sorted(files):
        source = repo / name
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(repo):
            raise SystemExit("Only regular repository files can be packaged.")
        snapshots[name] = (source.read_bytes(), 0o755 if source.stat().st_mode & 0o111 else 0o644)
    manifest = {"version": version, "commit": head, "uncommittedChanges": dirty,
                "files": {name: hashlib.sha256(data).hexdigest() for name, (data, _) in snapshots.items()}}
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    label = f"candidate-{hashlib.sha256(manifest_bytes).hexdigest()[:12]}" if dirty else head[:12]
    directory = repo / "build/browser-client-distribution"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"overte-browser-client-{version}-{label}.tar.gz"
    temporary = output.with_suffix(".tmp")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=mtime) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    for name, (data, mode) in [*snapshots.items(), ("browser-client/BUILD_INFO.json", (manifest_bytes, 0o644))]:
                        info = tarfile.TarInfo(name)
                        info.size = len(data)
                        info.mode = mode
                        info.mtime = mtime
                        archive.addfile(info, io.BytesIO(data))
        # Refuse a concurrent source/build replacement rather than labeling a
        # mixed development snapshot as a reproducible deployment.
        if git(repo, "rev-parse", "HEAD").decode().strip() != head or any(
                (repo / name).read_bytes() != data for name, (data, _) in snapshots.items()):
            raise SystemExit("Sources changed during packaging; retry after builds and edits finish.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".sha256").write_text(f"{checksum}  {output.name}\n")
    print(json.dumps({"filename": output.name, "bytes": output.stat().st_size,
                      "sha256": checksum, "files": len(snapshots), "uncommittedChanges": dirty}))


if __name__ == "__main__":
    main()
