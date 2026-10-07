<!-- Copyright 2026 Overte contributors; SPDX-License-Identifier: Apache-2.0 -->
<!-- AI-assisted preparation. Hardware commands and human acceptance remain unqualified. -->
# Manual hardware and speech acceptance

This is a proposed human-assisted procedure, not a completed hardware result.
The existing software journey, native interoperability and synthetic PCM tests
are recorded in [STATUS.md](STATUS.md). They do not establish intelligible
physical speech or fluid hardware rendering. Steps 2–5 below are **PROPOSED /
UNQUALIFIED**; only their syntax may be checked before the required resources exist.

## 1. Preconditions and already-tested components

A real available microphone/headphones and an explicitly agreed exclusive
cross-session GPU/desktop window are required. An idle snapshot is insufficient.
Do not use another session's display, GPU, profile, audio server or services.
Run from a terminal on the supplied user desktop with its normal host audio;
leave OS audio defaults unchanged. Two human listeners/headsets are preferable;
with one headset, alternate clients and enable only the originating microphone.

Reuse this worktree's qualified domain, six assignments, HTTPS fixture, original
83-entity scene and frozen complete browser distribution. Their existing launch
and validation commands are in [LAB.md](LAB.md); do not rebuild, prepare or restart
services for this procedure. The tested localhost Vite preview invocation is
reused below. Its hardware client environment has not been exercised.
Archive any current owned visitor observations separately, then, when its owner
has released it, use the existing tested `python3 browser-direct-client/lab/native-visitor.py stop`
to free its UDP port 46116. No automated browser run may be active on port 46106.
Preserve immutable journey logs, qualifications and consumed motion records.

## 2. Fresh private run directory — PROPOSED / UNQUALIFIED

From the repository root, in the supplied desktop terminal:

```bash
umask 077
export DIRECT_REPO="$(pwd -P)"
export MANUAL_DIR="$(mktemp -d "$DIRECT_REPO/build/browser-direct/manual-XXXXXX")"
export PLAYWRIGHT_BROWSERS_PATH="$DIRECT_REPO/build/browser-direct/browsers"
mkdir -p -m 700 "$MANUAL_DIR"/chrome-profile "$MANUAL_DIR"/{chrome,native}/{config,data,cache,tmp}
```

Use only the already-installed lockfile-selected Playwright Chrome and pinned
Overte 2026.04.1 AppRun. Do not download another binary. The launcher derives
Chrome's exact path through Playwright and trusts only the own fixture's SPKI.
Native Qt requires read-only process-local CA mounts: `SSL_CERT_FILE` alone
failed in this laboratory. The combined bundle retains system roots; the own
hosts overlay retains the standard native loopback STUN fallback. Neither file
changes host trust or `/etc/hosts`. No permission, media or blanket TLS bypass is used.

## 3. Owned preview and hardware clients — PROPOSED / UNQUALIFIED

Save and execute this per-run snippet. It reuses existing identity/start-tick
registration and bounded cleanup, with a separate private manual registry.
The native mount namespace retains actual hardware/desktop/audio access only
during the supplied exclusive window; it does not use displays 104/105 or private Pulse.

```bash
cat > "$MANUAL_DIR/launch.py" <<'PY'
import fcntl, hashlib, importlib.util, json, os, select, sys, time
from pathlib import Path
import shutil, socket, subprocess, tempfile, urllib.request
repo, run = Path(os.environ["DIRECT_REPO"]), Path(os.environ["MANUAL_DIR"])
client, lab = repo / "browser-direct-client", repo / "build/browser-direct/lab"
spec = importlib.util.spec_from_file_location("manual_owner", client / "e2e/run.py")
owner = importlib.util.module_from_spec(spec); spec.loader.exec_module(owner)
lock = (lab / "runtime/browser-tests.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
old = json.loads(owner.REGISTRY.read_text()) if owner.REGISTRY.exists() else {}
assert not any(owner.owns_process(i) for e in old.values() for i in [e["parent"], *e["children"]])
owner.REGISTRY = run / "processes.json"
native_state = json.loads((lab / "runtime/processes.json").read_text())
readiness = json.loads((lab / "runtime/assignment-readiness.json").read_text())
runtime = json.loads((lab / "runtime/native-runtime.json").read_text())
for name, field in (("domain", "domain"), ("assignments", "assignments")):
    identity = native_state[name]
    assert owner.owns_process(identity)
    assert readiness[field + "PID"] == identity["pid"] and readiness[field + "StartTicks"] == identity["startTicks"]
assert readiness["runtimeSHA256"] == runtime["runtimeSHA256"]
assert readiness["adminAuthenticated"] is True and readiness["stableSeconds"] >= 3
assert {"audio-mixer", "avatar-mixer", "asset-server", "messages-mixer",
        "entity-server", "entity-script-server"}.issubset(readiness["assignmentTypes"])
for kind, address, port in ((socket.SOCK_STREAM, "127.0.0.1", 46106),
                            (socket.SOCK_DGRAM, "0.0.0.0", 46116)):
    with socket.socket(socket.AF_INET, kind) as probe: probe.bind((address, port))
env = dict(os.environ)
for key in ("PULSE_SERVER", "PULSE_SOURCE", "PULSE_SINK", "LIBGL_ALWAYS_SOFTWARE",
            "GALLIUM_DRIVER", "QT_QPA_PLATFORM", "QTWEBENGINE_CHROMIUM_FLAGS"):
    env.pop(key, None)
assert env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"), "Use the supplied desktop terminal"
cert = lab / "runtime/fixture-tls/cert.pem"
script = "import {chromium} from '@playwright/test'; import{readFileSync}from'node:fs'; import{X509Certificate,createHash}from'node:crypto'; const c=new X509Certificate(readFileSync(process.argv[1])); console.log(JSON.stringify({exe:chromium.executablePath(),pin:createHash('sha256').update(c.publicKey.export({type:'spki',format:'der'})).digest('base64')}));"
chrome = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script, str(cert)], cwd=client, env=env))
native, hosts = lab / "native-release/squashfs-root/AppRun", lab / "runtime/native-hosts"
assert Path(chrome["exe"]).is_file() and native.is_file() and hosts.is_file()
assert hosts.read_text().startswith("127.0.0.1 stun1.l.google.com\n")
roots = next(p for p in (Path("/etc/pki/tls/certs/ca-bundle.crt"), Path("/etc/ssl/certs/ca-certificates.crt")) if p.is_file())
ca, own_hosts = run / "ca.pem", run / "native-hosts"
ca.write_bytes(roots.read_bytes().rstrip() + b"\n" + cert.read_bytes()); own_hosts.write_bytes(hosts.read_bytes())
qualified = repo / "build/browser-direct/e2e/direct-chrome-20261003-g"
manifest_bytes = (qualified / "bundle-manifest.json").read_bytes()
assert hashlib.sha256(manifest_bytes).hexdigest() == "b9e763d1dcff0f2ce8d99bda8a05610cbcc236e41e5a5f1d48026c0c476c3d4b"
bundle = qualified / "bundle"
assert not any(p.is_symlink() for p in bundle.rglob("*"))
files = [{"path": str(p.relative_to(bundle)), "bytes": p.stat().st_size,
          "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(bundle.rglob("*")) if p.is_file()]
assert files == json.loads(manifest_bytes) and len(files) == 40
(run / "bundle-manifest.json").write_bytes(manifest_bytes)
def private_environment(kind):
    return {**env, **{f"XDG_{name.upper()}_HOME": str(run / kind / name)
                     for name in ("config", "data", "cache")},
            "TMPDIR": str(run / kind / "tmp")}
native_env = {**private_environment("native"), "SSL_CERT_FILE": str(ca), "CURL_CA_BUNDLE": str(ca)}
chrome_env = private_environment("chrome")
mounts = ["bwrap", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--die-with-parent", "--new-session", "--ro-bind", "/", "/", "--bind", str(run), str(run), "--tmpfs", "/dev/shm", "--proc", "/proc", "--ro-bind", str(own_hosts), "/etc/hosts"]
targets = {str(Path(p).resolve()) for p in ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem") if Path(p).is_file()}
assert targets
for target in sorted(targets): mounts += ["--ro-bind", str(ca), target]
native_command = mounts + ["--chdir", str(repo), "--", str(native), "--allowMultipleInstances", "--url", "hifi://127.0.0.3:46102", "--listenPort", "46116", "--cache", str(run / "native/cache"), "--no-updater", "--no-login-suggestion", "--suppress-settings-reset", "--disableDisplayPlugins", "OpenXR,OpenVR,OpenVR (Vive)", "--disableInputPlugins", "OpenXR,OpenVR,OpenVR (Vive),SDL2", "--displayName", "manual-native"]
state = {}; begin_cleanup, restore = owner.install_launcher_interruption_handlers()
short_tmp = None
def start_owned(name, command, environment):
    # Keep the registered Python executable/cwd fixed across bwrap/AppRun execs.
    supervisor = [sys.executable, "-c", "import subprocess,sys; raise SystemExit(subprocess.call(sys.argv[1:],stdin=subprocess.DEVNULL))"]
    return owner.start(state, name, supervisor + command, environment, run / (name + ".log"))
try:
    # Chrome's singleton Unix-socket path requires a short owned TMPDIR.
    short_tmp = tempfile.mkdtemp(prefix="overte-direct-manual-", dir="/tmp")
    chrome_env["TMPDIR"] = short_tmp
    (run / "chrome-temporary-directory.txt").write_text(short_tmp + "\n")
    version = subprocess.check_output([chrome["exe"], "--version"], cwd=client, env=chrome_env, text=True, timeout=10).strip()
    assert version.split()[-1] == "153.0.8010.12", "The installed Chrome version differs from the qualified version"
    (run / "chrome-version.txt").write_text(version + "\n")
    processes = [start_owned("http", ["node", str(client / "node_modules/vite/bin/vite.js"), "preview", "--host", "127.0.0.1", "--port", "46106", "--strictPort", "--outDir", str(bundle)], env)]
    ready = False; startup_deadline = time.monotonic() + 10
    while time.monotonic() < startup_deadline and processes[0].poll() is None:
        owner.refresh(state)
        try:
            with urllib.request.urlopen("http://127.0.0.1:46106/", timeout=1) as response:
                ready = response.status == 200 and response.read() == (bundle / "index.html").read_bytes()
        except (OSError, TimeoutError): pass
        if ready: break
        time.sleep(0.1)
    assert ready and processes[0].poll() is None, "Own preview did not serve the qualified index within 10 seconds"
    processes += [start_owned("native", native_command, native_env)]
    processes += [start_owned("chrome", [chrome["exe"], "--user-data-dir=" + str(run / "chrome-profile"), "--no-first-run", "--password-store=basic", "--ignore-certificate-errors-spki-list=" + chrome["pin"], "http://127.0.0.1:46106/?server=ws%3A%2F%2F127.0.0.1%3A46104"], chrome_env)]
    deadline = time.monotonic() + 1200
    print("Finish within the supplied window (maximum 20 minutes); press Enter here to clean up.")
    while time.monotonic() < deadline and all(p.poll() is None for p in processes):
        owner.refresh(state)
        if select.select([sys.stdin], [], [], 0.5)[0]: break
finally:
    begin_cleanup()
    try:
        owner.stop(state)
        if short_tmp is not None: shutil.rmtree(short_tmp)
    finally: restore()
PY
python3 "$MANUAL_DIR/launch.py"
```

If startup fails, inspect only this run's private logs and stop; do not change
other services, remove native gates or add sandbox/graphics bypass flags.

## 4. Human acceptance and evidence — PROPOSED / UNQUALIFIED

Join `ws://127.0.0.1:46104` in the browser tablet. Keep original model/texture
quality, default graphics and image sharing: no resolution, model or map reduction.
Wait for the same 83 entities, 55 models/available maps and original skybox; retain
the known unavailable-PSD warning honestly. In native Avatar settings select
`https://127.0.0.1:46119/default-avatar/defaultAvatar_full.fst` if necessary.
Both humans approach normally; do not use observer scripts, teleports or motion trials.

In Chrome DevTools record the actual renderer from the existing world canvas:

```js
const gl = document.querySelector('#world canvas').getContext('webgl2');
const ext = gl.getExtension('WEBGL_debug_renderer_info');
const renderer = ext && gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
const {performance, audio} = window.overteDirectDiagnostics();
console.log({renderer, fps:performance.fps, medianFrameMs:performance.medianFrameMs,
  p95FrameMs:performance.p95FrameMs, samples:performance.samples, audio});
```

An unavailable renderer or SwiftShader/llvmpipe/swrast/software is not hardware proof.
Select actual input/output in Chrome's own profile settings and native Audio UI;
verify physical headphones and the chosen physical microphone, not a monitor/remap source.
Click Microphone, answer the real permission prompt, and record Allow/track lifetime.
Speak an unplanned phrase browser→native; the listener repeats it. Reverse
native→browser with only that sender unmuted. Record intelligibility, delay/echo,
mute/unmute and browser Leave stopping capture/playback. PCM counters alone are insufficient.
For 60–120 seconds use real WASD/mouse, Space jump, collision, E interaction,
V avatar view and T tablet. Record perceived responsiveness and frame snapshots
after loading/during movement; metrics cover the latest 240 intervals, not the whole trial.
Keep timestamps, bundle hashes, quality settings and separate PASS/FAIL/NOT RUN
speech/navigation notes under this run directory. Sanitize identities before publishing.

## 5. Cleanup — PROPOSED / UNQUALIFIED

Mute both clients, leave the browser domain, then press Enter in the launch terminal
within the exclusive window. Ctrl-C/TERM also enters the existing bounded cleanup.
It signals only recorded processes whose PID, start ticks, executable, working
directory and group still match; it never uses global `pkill` or stops the domain.
Confirm this run's `processes.json` is empty and its owned windows/capture are gone.
Retain private evidence without rewriting historical results. Report hardware
fluidity and physical speech only after these actual human observations succeed.
