# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Test-only host PID qualification and two fixed native pose setup operations.

The browser's private PID namespace stays intact. No page, application, network
endpoint or arbitrary executable/argument is exposed by this private file relay.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time
import uuid


def read_native_observation(path: Path) -> dict:
    with path.open("rb") as source:
        source.seek(0, 2)
        size = source.tell()
        source.seek(max(0, size - 262144))
        text = source.read(262144).decode("utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        if "DIRECT_LAB_NATIVE " in line:
            try:
                return json.loads(line.split("DIRECT_LAB_NATIVE ", 1)[1])
            except json.JSONDecodeError:
                pass
    return {}


def identity_label(identity: dict) -> dict:
    return {key: identity[key] for key in ("pid", "startTicks", "executable", "cwd")}


class NativeHostActions:
    """Only move once and restore once in an independently pinned native session."""
    def __init__(self, directory: Path, identity: dict, session: str, visitor,
                 observed, live, launch, cancel, maximum_job_seconds: float = 12):
        self.directory = directory
        self.requests = directory / "requests"
        self.results = directory / "results"
        self.identity = dict(identity)
        self.session = session
        self.run_nonce = str(uuid.uuid4())
        self.visitor, self.observed, self.live = visitor, observed, live
        self.launch, self.cancel = launch, cancel
        self.maximum_job_seconds = maximum_job_seconds
        self.seen: set[str] = set()
        self.jobs: dict[str, dict] = {}
        self.move_started = False
        self.restore_started = False
        self.closed = False
        self.last_proof = 0.0
        for path in (directory, self.requests, self.results):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def write(path: Path, value: dict) -> None:
        temporary = path.with_suffix(".pending")
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)

    def qualify(self) -> dict:
        visitor, observed = self.visitor(), self.observed()
        if visitor.get("release") != "2026.04.1" or visitor.get("parent") != self.identity or not self.live(self.identity):
            raise RuntimeError("The exact registered host native PID/start tick/executable/cwd changed or stopped")
        when = observed.get("observedAtUnixTime", 0)
        if observed.get("connected") is not True or observed.get("session") != self.session or \
                observed.get("nativeMotionControlVersion") != 2 or \
                type(observed.get("sequence")) is not int or not 0 <= observed["sequence"] < 2 ** 53 or \
                not isinstance(when, (int, float)) or not math.isfinite(when) or not 0 <= time.time() - when <= 6:
            raise RuntimeError("The pinned native session must have a fresh connected observer sample")
        return observed

    def proof(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.last_proof < 1:
            return
        self.last_proof = time.monotonic()
        result = {"hostObservedUnixTime": time.time(), "processIdentity": identity_label(self.identity),
                  "nativeSession": self.session, "runNonce": self.run_nonce,
                  "source": "Host /proc live identity and fresh actual native observer",
                  "browserPrivatePIDNamespacePreserved": True, "live": False, "closed": self.closed}
        try:
            observed = self.qualify()
            result.update(live=not self.closed, nativeObservedSequence=observed["sequence"], nativeMotionControlVersion=2)
        except (OSError, KeyError, RuntimeError, ValueError) as error:
            result["error"] = str(error)[:1024]
        self.write(self.directory / "host-proof.json", result)

    def reply(self, request_id: str, result: dict) -> None:
        self.write(self.results / (request_id + ".json"), {"requestId": request_id,
            "hostCompletedUnixTime": time.time(), "processIdentity": identity_label(self.identity),
            "runNonce": self.run_nonce, **result})

    def accept(self, path: Path) -> None:
        request_id = path.stem
        if request_id in self.seen:
            return
        if str(uuid.UUID(request_id)) != request_id:
            return
        if len(self.seen) >= 4:
            return
        self.seen.add(request_id)
        try:
            # A FIFO or exchanged symlink must never block the host watchdog.
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > 4096 or \
                        metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                    raise RuntimeError("The private action request is not an owned, 0600 bounded regular file")
                content = os.read(descriptor, 4097)
                if len(content) > 4096:
                    raise RuntimeError("The native request exceeded its bound")
            finally:
                os.close(descriptor)
            request = json.loads(content)
            if set(request) != {"requestId", "operation", "nativeSession", "processIdentity", "issuedUnixTime", "runNonce"} or \
                    request["requestId"] != request_id:
                raise RuntimeError("Unexpected native action fields")
            if request["runNonce"] != self.run_nonce:
                raise RuntimeError("Native action nonce does not bind this host test run")
            when = request["issuedUnixTime"]
            if not isinstance(when, (int, float)) or not math.isfinite(when) or not 0 <= time.time() - when <= 5:
                raise RuntimeError("Expired native test action")
            if request["nativeSession"] != self.session or request["processIdentity"] != identity_label(self.identity):
                raise RuntimeError("Native test action does not bind the pinned host process/session")
            operation = request["operation"]
            if operation not in ("motion-move", "motion-restore"):
                raise RuntimeError("Only the two fixed native test pose operations are allowed")
            self.qualify()
            if self.jobs:
                raise RuntimeError("A bounded native test operation is already active")
            if operation == "motion-move":
                if self.move_started:
                    raise RuntimeError("Only one native move is allowed")
                self.move_started = True
            else:
                if not self.move_started or self.restore_started:
                    raise RuntimeError("Restore requires the current once-moved native trial")
                self.restore_started = True
            self.start_job(request_id, operation)
        except (OSError, KeyError, RuntimeError, ValueError, TypeError) as error:
            self.reply(request_id, {"ok": False, "error": str(error)[:2048]})

    def start_job(self, request_id: str, operation: str) -> None:
        output = self.directory / (request_id + ".log")
        name = "native-action-" + request_id
        process = self.launch(name, operation, output)
        self.jobs[request_id] = {"process": process, "name": name, "operation": operation,
                                 "output": output, "deadline": time.monotonic() + self.maximum_job_seconds}

    def finish_jobs(self) -> None:
        for request_id, job in list(self.jobs.items()):
            process = job["process"]
            if process.poll() is None and time.monotonic() <= job["deadline"]:
                continue
            try:
                if process.poll() is None:
                    self.cancel(job["name"])
                    process.wait(timeout=3)
                    raise RuntimeError("The bounded native host operation timed out")
                if process.returncode != 0:
                    raise RuntimeError("The guarded native helper rejected the test operation; inspect its private log")
                output = job["output"]
                if output.stat().st_size > 32768:
                    raise RuntimeError("Native helper output exceeded its bound")
                result = json.loads(output.read_text().strip())
                self.qualify()
                if result.get("session") != self.session or result.get("browserMoved") is not False or \
                        result.get("operation") != job["operation"].removeprefix("motion-"):
                    raise RuntimeError("Native helper response did not bind the expected operation/session")
                self.reply(request_id, {"ok": True, "operation": job["operation"], "result": result})
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                self.reply(request_id, {"ok": False, "error": str(error)[:2048]})
            del self.jobs[request_id]

    def tick(self) -> None:
        self.proof()
        self.finish_jobs()
        # At most four requests are retained; there is no arbitrary command queue.
        for path in sorted(self.requests.glob("*.json"))[:8]:
            try:
                self.accept(path)
            except ValueError:
                pass

    def close(self) -> None:
        if self.closed:
            return
        # Finish/expire the owned setup operation before checking compensation.
        while self.jobs:
            self.finish_jobs()
            if self.jobs:
                time.sleep(0.05)
        try:
            observed = self.qualify()
            if self.move_started and (observed.get("nativeMotionTest") or {}).get("phase") == "moved":
                cleanup_id = str(uuid.uuid4())
                self.write(self.directory / "cleanup-restore.json", {"requestId": cleanup_id,
                    "operation": "motion-restore", "nativeSession": self.session, "runNonce": self.run_nonce,
                    "label": "Restore owned setup after driver exit"})
                self.start_job(cleanup_id, "motion-restore")
                while self.jobs:
                    self.finish_jobs()
                    if self.jobs:
                        time.sleep(0.05)
        except (OSError, KeyError, RuntimeError, TypeError, ValueError) as error:
            self.write(self.directory / "cleanup-error.json", {"error": str(error)[:2048]})
        self.closed = True
        self.proof(True)
