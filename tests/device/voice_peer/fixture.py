"""Owned Linux PC partner fixture; separate profile, host lock, bounded cleanup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

CLI = Path(__file__).with_name("voice_peer.py")


def invoke(state: Path, action: str, **arguments) -> dict:
    command = [sys.executable, str(CLI), "--state-dir", str(state), action]
    for key, value in arguments.items():
        command += ["--" + key.replace("_", "-"), str(value)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=80)
    except subprocess.TimeoutExpired:
        raise RuntimeError("owned PC voice operation timed out") from None
    if completed.returncode not in (0, 1):
        diagnostic = state / "last-cli-error.private.json"
        diagnostic.write_text(json.dumps({"exitCode": completed.returncode,
                                         "stderr": completed.stderr[:16384]}))
        diagnostic.chmod(0o600)
        raise RuntimeError("owned PC voice operation failed")
    try:
        return json.loads(completed.stdout)
    except ValueError:
        raise RuntimeError("owned PC voice operation returned invalid metadata") from None


class VoicePeerFixture:
    def __init__(self, config: Path, domain: str, diagnostics_dir: Path | None = None):
        if sys.platform != "linux":
            raise RuntimeError("the owned PC voice fixture requires Linux")
        metadata = config.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600):
            raise ValueError("voice peer configuration must be a private current-user file")
        self.config, self.domain = config, domain
        self.diagnostics_dir = diagnostics_dir
        self.temporary = None
        self.lock = None
        self.state = None
        self.process = None
        self.log = None

    def start(self, cancelled=lambda: False) -> dict[str, str]:
        if sys.platform != "linux":
            raise RuntimeError("the owned PC voice fixture requires Linux")
        import fcntl
        lock_root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "overte-voice-lab"
        if lock_root.is_symlink():
            raise RuntimeError("voice resource directory must not be a symbolic link")
        lock_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = lock_root.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise RuntimeError("voice resource directory must be private and current-user-owned")
        descriptor = os.open(lock_root / "resource.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(descriptor, "a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.temporary = tempfile.TemporaryDirectory(prefix="overte-owned-voice-")
            self.state = Path(self.temporary.name)
            self.log = (self.state / "supervisor.log").open("wb")
            self.process = subprocess.Popen(
                [sys.executable, str(CLI), "--state-dir", str(self.state), "serve",
                 "--launch-config", str(self.config), "--domain", self.domain],
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
                start_new_session=True)
            deadline = time.monotonic() + 45
            stable_since = None
            stable_samples = 0
            previous_sequence = 0
            while time.monotonic() < deadline:
                if cancelled():
                    raise RuntimeError("owned PC voice fixture startup was cancelled")
                if self.process.poll() is not None:
                    raise RuntimeError("owned PC voice supervisor exited before readiness")
                if not (self.state / "session.json").is_file():
                    time.sleep(0.1)
                    continue
                status = invoke(self.state, "status")
                client = status.get("client") or {}
                sequence = client.get("sequence", 0)
                age = status.get("snapshotAgeSeconds")
                ready = (status.get("snapshotFresh") and status.get("audioRouted")
                         and client.get("connected") and client.get("mixerReady")
                         and type(age) in (int, float) and age <= 1.0)
                if ready and type(sequence) is int and sequence > previous_sequence:
                    previous_sequence = sequence
                    stable_samples += 1
                    if stable_since is None:
                        stable_since = time.monotonic()
                    # Cold Interface startup can publish a first snapshot before
                    # startup work settles. Require a sustained advancing
                    # probe with verified routes, not just that first heartbeat.
                    if stable_samples >= 8 and time.monotonic() - stable_since >= 3:
                        return {"OVERTE_E2E_VOICE_PEER_STATE": str(self.state), "OVERTE_E2E_VOICE_TESTS": "1"}
                elif not ready:
                    stable_since = None
                    stable_samples = 0
                time.sleep(0.2)
            raise RuntimeError("owned PC voice partner did not connect to the mixer")
        except BlockingIOError:
            self.close()
            raise RuntimeError("the shared PC audio fixture is already reserved") from None
        except BaseException:
            try:
                self.preserve_failure_diagnostics()
            finally:
                self.close()
            raise

    def preserve_failure_diagnostics(self) -> None:
        if self.diagnostics_dir is None or self.state is None:
            return
        destination = self.diagnostics_dir
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = destination.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            raise RuntimeError("PC voice diagnostics directory must be private")
        # Retain only bounded diagnostics, never session tokens or generated
        # authenticated runtime scripts. These files remain local and private.
        for name in ("supervisor.log", "client.log", "last-cli-error.private.json", "last-command-error.json"):
            source = self.state / name
            if source.is_symlink() or not source.is_file():
                continue
            descriptor = os.open(destination / name,
                                 os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with source.open("rb") as inp, os.fdopen(descriptor, "wb") as out:
                inp.seek(max(0, source.stat().st_size - 8 * 1024 * 1024))
                shutil.copyfileobj(inp, out)
            (destination / name).chmod(0o600)

    def close(self) -> None:
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    # The fixture owns the foreground supervisor, including
                    # readiness failures before it publishes a control token.
                    self.process.terminate()
                try:
                    self.process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    raise RuntimeError("owned PC voice cleanup did not finish; private state retained") from None
                if self.state is not None and (self.state / "session.json").exists():
                    raise RuntimeError("owned PC voice cleanup left its session state")
                self.process = None
            if self.log is not None:
                self.log.close()
                self.log = None
            if self.temporary is not None:
                # A portable module may fail an audio assertion while this
                # supervisor exits cleanly. Retain bounded private diagnostics
                # for that outcome before removing the owned temporary state.
                self.preserve_failure_diagnostics()
                self.temporary.cleanup()
                self.temporary = None
                self.state = None
        finally:
            if self.lock is not None:
                self.lock.close()
                self.lock = None
