"""Private, fail-closed reporting primitives for the iOS release gate."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GROUPS = {
    "secrets": "Secrets & Privacy",
    "hygiene": "Repository Hygiene",
    "licenses": "Licenses & Branding",
    "dependencies": "Dependencies & Supply Chain",
    "static": "Static Analysis",
    "configuration": "iOS Configuration",
    "permissions": "Permissions & Privacy Manifest",
    "signing": "Signing & Entitlements",
    "build": "Clean Build",
    "artifact": "APP/IPA Analysis",
    "functional": "Functional E2E Tests",
    "robustness": "Robustness Tests",
    "long-running": "Long-Running Tests",
    "distribution": "Distribution Readiness",
}
STATIC = tuple(list(GROUPS)[:8])


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def private_directory(path: Path):
    path = path.expanduser().absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("private directory must not use symlinks")
    if path == ROOT or ROOT in path.parents:
        raise ValueError("output must be outside the checkout")
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    path.chmod(0o700)
    return path


def git(*args, root=ROOT) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   stderr=subprocess.DEVNULL).decode("utf-8")


class Context:
    def __init__(self, config, output, selected):
        self.config, self.output, self.selected = config, output, selected
        self.revision = git("rev-parse", "HEAD").strip()
        self.findings = []
        self.inventories = {}
        self.group = "configuration"
        self.allowlist = json_read(HERE / "allowlist.json")["entries"]
        self.started = dt.datetime.now(dt.timezone.utc).isoformat()
        self.artifact = None
        self.artifact_sha = None
        self.build_dir = None
        self.build_source = None
        self.tool_versions = {}
        self.used_allowlist = set()
        for entry in self.allowlist:
            if (set(entry) != {"fingerprint", "reason", "owner", "expires"}
                    or len(entry["fingerprint"]) != 64
                    or not entry["reason"].strip() or not entry["owner"].strip()):
                raise ValueError("invalid allowlist entry")
            if dt.date.fromisoformat(entry["expires"]) < dt.date.today():
                raise ValueError("expired allowlist entry")

    def add(self, rule, status, path="", line=0, message="", next_step="Review the private report.",
            critical=False, evidence="", suppressible=False):
        # Never store matched source text: it may be a credential or personal data.
        fp = hashlib.sha256(f"{self.group}\0{rule}\0{path}\0{line}\0{evidence}".encode()).hexdigest()
        finding = dict(group=self.group, rule=rule, status=status, file=path, line=line,
                       description=message, nextStep=next_step, iosCritical=critical,
                       distributionCritical=critical, fingerprint=fp)
        if suppressible:
            for entry in self.allowlist:
                if entry["fingerprint"] == fp:
                    finding.update(status="WARNING", suppressed=True, disposition=entry)
                    self.used_allowlist.add(fp)
                    break
        self.findings.append(finding)

    def need(self, condition, rule, message, path="", next_step="Supply the missing evidence."):
        if not condition:
            self.add(rule, "FAIL", path, message=message, next_step=next_step, critical=True)
        return bool(condition)

    def command(self, name, argv, *, cwd=ROOT, env=None, timeout=1800, ok=(0,), log=True):
        executable = shutil.which(str(argv[0]))
        if not executable:
            self.add("tool-missing", "FAIL", message=f"Required tool unavailable: {name}",
                     next_step="Install the reviewed tool version; rerun this group.", critical=True)
            return None
        # No shell interpolation; all raw diagnostics are private and never echoed.
        with tempfile.TemporaryFile(dir=self.output) as stdout, tempfile.TemporaryFile(dir=self.output) as stderr:
            try:
                process = subprocess.Popen([str(v) for v in argv], cwd=cwd, env=env,
                                           stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    process.wait(timeout=timeout)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    # Stop the process tree; do not leave a build or device mutation running.
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    raise subprocess.TimeoutExpired(str(argv[0]), timeout) from None
            except (OSError, subprocess.TimeoutExpired):
                self.add("tool-error", "FAIL", message=f"{name} failed to execute or timed out.", critical=True)
                return None
            sizes = (stdout.tell(), stderr.tell())
            stdout.seek(0)
            stderr.seek(0)
            if log:
                target = self.output / f"{self.group}-{name}.private.log"
                with target.open("wb") as stream:
                    shutil.copyfileobj(stdout, stream)
                    stream.write(b"\n")
                    shutil.copyfileobj(stderr, stream)
                target.chmod(0o600)
                stdout.seek(0)
                stderr.seek(0)
            if max(sizes) > 128 * 1024 * 1024:
                self.add("tool-output-limit", "FAIL", message=f"{name} exceeded the bounded parser input size; raw log retained.", critical=True)
                return None
            result = subprocess.CompletedProcess([], process.returncode, stdout.read(), stderr.read())
        if result.returncode not in ok:
            self.add("tool-failure", "FAIL", message=f"{name} returned {result.returncode}.",
                     next_step=f"Inspect the private {self.group}-{name} log.", critical=True)
        return result

    def review(self, name, message, *, artifact=False):
        reviews = self.config.get("reviews", {})
        value = reviews.get(name, {})
        try:
            date_valid = dt.date.fromisoformat(value.get("expires", "")) >= dt.date.today()
        except (ValueError, TypeError):
            date_valid = False
        valid = (value.get("sourceRevision") == self.revision and value.get("accepted") is True
                 and isinstance(value.get("rationale"), str) and len(value["rationale"]) >= 20
                 and isinstance(value.get("reviewer"), str) and bool(value["reviewer"])
                 and date_valid)
        if artifact:
            valid = valid and self.artifact_sha and value.get("artifactSha256") == self.artifact_sha
        self.add("review-" + name, "WARNING" if valid else "FAIL", message=message,
                 next_step="Retain a revision-bound human review with rationale and expiry in the private config.",
                 critical=not valid)
        return valid

    def finish(self):
        categories = {}
        for key, title in GROUPS.items():
            rows = [x for x in self.findings if x["group"] == key]
            status = ("FAIL" if any(x["status"] == "FAIL" for x in rows) else
                      "WARNING" if any(x["status"] == "WARNING" for x in rows) else "PASS")
            if key not in self.selected:
                status = "WARNING"
            categories[key] = {"title": title, "status": status, "executed": key in self.selected,
                               "findings": len(rows)}
        complete = set(self.selected) == set(GROUPS)
        passed = complete and all(x["status"] != "FAIL" for x in categories.values())
        result = "IOS RELEASE CHECK: " + ("PASS" if passed else "FAIL")
        report = dict(schemaVersion=1, sourceRevision=self.revision, started=self.started,
                      artifactSha256=self.artifact_sha, complete=complete, result=result,
                      categories=categories, findings=self.findings, toolVersions=self.tool_versions,
                      unusedAllowlist=sorted({x["fingerprint"] for x in self.allowlist} - self.used_allowlist))
        write_json(self.output / "report.json", report)
        lines = ["# iOS release readiness", "", f"Source: `{self.revision}`", "",
                 "Private report. Do not publish raw diagnostics or inventories.", "",
                 "| Category | Status | Executed | Findings |", "| --- | --- | --- | --- |"]
        lines += [f"| {x['title']} | {x['status']} | {x['executed']} | {x['findings']} |" for x in categories.values()]
        lines += ["", "## Findings", ""]
        for group in self.selected:
            rows = [x for x in self.findings if x["group"] == group]
            failures = [x for x in rows if x["status"] == "FAIL"]
            warnings = [x for x in rows if x["status"] == "WARNING"]
            displayed = failures[:20] + warnings[:10]
            lines += [f"### {GROUPS[group]}", "", f"{len(failures)} failures; {len(warnings)} warnings. Full details: [report.json](report.json).", ""]
            for row in displayed:
                location = f"{row['file']}:{row['line']}".replace("`", "'")
                lines += [f"- **{row['status']}** `{row['rule']}` — `{location}`: {row['description']} "
                          f"Next: {row['nextStep']} Fingerprint: `{row['fingerprint']}`."]
            if len(rows) > len(displayed):
                lines += ["", f"{len(rows) - len(displayed)} additional findings retained in JSON; none excluded from the gate."]
            lines.append("")
        lines += ["", result, ""]
        (self.output / "report.md").write_text("\n".join(lines), encoding="utf-8")
        for name, data in self.inventories.items():
            write_json(self.output / f"{name}.json", data)
        print(result)
        if not complete:
            print("Partial inspection only; unexecuted categories prevent release approval.")
        # Partial successful checks remain useful to local/CI callers; never print release PASS.
        return 0 if not any(x["status"] == "FAIL" for x in self.findings) else 1
