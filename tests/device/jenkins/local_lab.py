#!/usr/bin/env python3
"""Install and run the pinned, localhost-only Overte Jenkins device lab."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
DEVICE_ROOT = HERE.parent
REPOSITORY = DEVICE_ROOT.parents[1]
LOCK_FILE = DEVICE_ROOT / "toolchain.lock.json"
PLUGINS_FILE = HERE / "plugins.lock.txt"
PLUGIN_ARTIFACTS_FILE = HERE / "plugins.artifacts.lock.json"
JENKINS_TEMPLATE = HERE / "jenkins.yaml"
MAX_DOWNLOAD_BYTES = 768 * 1024 * 1024
NODE_NAME = "overte-device-local"
ADMIN_ID = "overte-admin"


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def secure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    return path.resolve()


def secure_write(path: Path, value: str) -> None:
    parent = secure_directory(path.parent)
    destination = parent / path.name
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(name)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = -1
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def download(artifact: dict, destination: Path) -> Path:
    expected = artifact.get("sha256")
    url = artifact.get("url")
    if (not isinstance(url, str) or not url.startswith("https://")
            or not isinstance(expected, str) or len(expected) != 64):
        fail("toolchain lock contains an invalid artifact")
    if destination.is_file() and sha256(destination) == expected:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "overte-device-lab-bootstrap/1"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                fail("tool artifact exceeds the download limit")
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_DOWNLOAD_BYTES:
                    fail("tool artifact exceeds the download limit")
                output.write(block)
    except (HTTPError, URLError, OSError, ValueError) as error:
        temporary.unlink(missing_ok=True)
        fail(f"could not download pinned tool artifact: {type(error).__name__}")
    if sha256(temporary) != expected:
        temporary.unlink(missing_ok=True)
        fail("downloaded tool artifact failed its pinned SHA-256")
    temporary.replace(destination)
    return destination


def load_lock() -> dict:
    value = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1:
        fail("unsupported toolchain lock schema")
    return value


def java_major(java: Path) -> int:
    result = subprocess.run([str(java), "-version"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=15, check=False)
    first = result.stdout.splitlines()[0] if result.stdout else ""
    try:
        token = first.split('"', 2)[1].split(".", 1)[0]
        return int(token)
    except (IndexError, ValueError):
        fail("could not determine the configured Java version")


def paths(arguments: argparse.Namespace) -> dict[str, Path]:
    install = secure_directory(Path(arguments.install_root).expanduser())
    config = secure_directory(Path(arguments.config_root).expanduser())
    return {
        "install": install,
        "config": config,
        "artifacts": secure_directory(install / "artifacts"),
        "jenkinsHome": secure_directory(config / "jenkins-home"),
        "agentRoot": secure_directory(config / "agent"),
        "state": config / "local-lab.json",
        "password": config / "admin-password",
        "casc": config / "jenkins.yaml",
    }


def install_plugins(java: Path, manager: Path, war: Path, home: Path) -> None:
    command = [str(java), "-jar", str(manager), "--war", str(war),
               "--plugin-download-directory", str(home / "plugins"),
               "--plugin-file", str(PLUGINS_FILE), "--latest=false"]
    subprocess.run(command, cwd=REPOSITORY, timeout=900, check=True)
    locked = json.loads(PLUGIN_ARTIFACTS_FILE.read_text(encoding="utf-8"))
    for plugin in locked.get("plugins", []):
        candidates = [home / "plugins" / f"{plugin['id']}.jpi",
                      home / "plugins" / f"{plugin['id']}.hpi"]
        installed = next((item for item in candidates if item.is_file()), None)
        if installed is None or sha256(installed) != plugin["sha256"]:
            fail(f"installed Jenkins plugin failed its pin: {plugin['id']}")


def install_appium(lock: dict, install_root: Path, appium_home: Path, npm: str) -> Path:
    appium = lock["appium"]
    root = secure_directory(install_root / "appium")
    package = {
        "private": True,
        "name": "overte-device-lab-appium",
        "version": "1.0.0",
        "dependencies": {
            appium["core"]["package"]: appium["core"]["version"],
        },
    }
    (root / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    subprocess.run([npm, "install", "--ignore-scripts=false", "--no-audit", "--no-fund",
                    "--save-exact"], cwd=root, timeout=900, check=True)
    executable = root / "node_modules" / ".bin" / ("appium.cmd" if os.name == "nt" else "appium")
    if not executable.is_file():
        fail("pinned Appium installation did not create its executable")
    environment = os.environ.copy()
    environment["APPIUM_HOME"] = str(secure_directory(appium_home))
    listed = subprocess.run([str(executable), "driver", "list", "--installed", "--json"],
                            env=environment, text=True, stdout=subprocess.PIPE,
                            timeout=60, check=True)
    installed = json.loads(listed.stdout)
    for name, driver in appium["drivers"].items():
        current = installed.get(name, {}) if isinstance(installed, dict) else {}
        if current.get("version") == driver["version"]:
            continue
        if current:
            subprocess.run([str(executable), "driver", "uninstall", name],
                           env=environment, timeout=180, check=True)
        subprocess.run([str(executable), "driver", "install",
                        f"{name}@{driver['version']}", "--json"],
                       env=environment, timeout=900, check=True)
    ios_runtime = appium.get("iosRuntime", {})
    runtime_specs = [
        f"{entry['package']}@{entry['version']}"
        for entry in ios_runtime.values()
    ]
    if runtime_specs:
        subprocess.run(
            [npm, "install", "--ignore-scripts=false", "--no-audit", "--no-fund",
             "--save-exact", *runtime_specs],
            cwd=appium_home,
            timeout=900,
            check=True,
        )
        for name, entry in ios_runtime.items():
            package_file = appium_home / "node_modules" / entry["package"] / "package.json"
            if not package_file.is_file():
                fail(f"pinned Appium iOS runtime was not installed: {name}")
            installed_package = json.loads(package_file.read_text(encoding="utf-8"))
            if installed_package.get("version") != entry["version"]:
                fail(f"installed Appium iOS runtime failed its exact pin: {name}")
    return executable


def render_casc(location: dict[str, Path]) -> None:
    source = JENKINS_TEMPLATE.read_text(encoding="utf-8")
    rendered = source.replace("__OVERTE_ADMIN_PASSWORD_FILE__",
                              location["password"].as_posix())
    rendered = rendered.replace("__OVERTE_AGENT_ROOT__", location["agentRoot"].as_posix())
    if any(token in rendered for token in (
            "__OVERTE_ADMIN_PASSWORD_FILE__", "__OVERTE_AGENT_ROOT__")):
        fail("Jenkins JCasC template contains an unresolved token")
    secure_write(location["casc"], rendered)


def install(arguments: argparse.Namespace) -> int:
    lock = load_lock()
    location = paths(arguments)
    java = Path(arguments.java).expanduser().resolve()
    if not java.is_file() or java_major(java) not in lock["jenkins"]["javaMajors"]:
        fail("Jenkins Java is missing or not one of the pinned supported majors")

    war = download(lock["jenkins"]["lts"]["artifact"],
                   location["artifacts"] / "jenkins.war")
    manager_version = lock["jenkins"]["pluginInstallationManager"]["version"]
    manager = download(lock["jenkins"]["pluginInstallationManager"]["artifact"],
                       location["artifacts"] / f"jenkins-plugin-manager-{manager_version}.jar")
    install_plugins(java, manager, war, location["jenkinsHome"])
    appium_home = secure_directory(location["config"] / "appium-home")
    appium = None if arguments.skip_appium else install_appium(
        lock, location["install"], appium_home, arguments.npm)

    if not location["password"].exists():
        secure_write(location["password"], secrets.token_urlsafe(32) + "\n")
    render_casc(location)
    state = {
        "schemaVersion": 1,
        "repository": str(REPOSITORY),
        "java": str(java),
        "jenkinsWar": str(war),
        "jenkinsHome": str(location["jenkinsHome"]),
        "agentRoot": str(location["agentRoot"]),
        "casc": str(location["casc"]),
        "adminId": ADMIN_ID,
        "adminPasswordFile": str(location["password"]),
        "serverUrl": f"http://127.0.0.1:{arguments.port}",
        "appiumExecutable": str(appium) if appium else None,
        "appiumHome": str(appium_home),
    }
    secure_write(location["state"], json.dumps(state, indent=2, sort_keys=True) + "\n")
    print(f"Installed pinned device-lab software in {location['install']}")
    print(f"Wrote private local configuration to {location['config']}")
    return 0


def read_state(arguments: argparse.Namespace) -> dict:
    state = Path(arguments.config_root).expanduser().resolve() / "local-lab.json"
    if not state.is_file():
        fail("local device lab is not installed")
    value = json.loads(state.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1:
        fail("unsupported local device-lab state")
    return value


def controller(arguments: argparse.Namespace) -> int:
    state = read_state(arguments)
    environment = os.environ.copy()
    environment.update({"JENKINS_HOME": state["jenkinsHome"],
                        "CASC_JENKINS_CONFIG": state["casc"]})
    command = [state["java"], "-Djenkins.install.runSetupWizard=false", "-jar",
               state["jenkinsWar"], "--httpListenAddress=127.0.0.1",
               f"--httpPort={state['serverUrl'].rsplit(':', 1)[1]}"]
    return subprocess.run(command, env=environment, check=False).returncode


def authenticated_request(state: dict, path: str, *, timeout: int = 30) -> bytes:
    password = Path(state["adminPasswordFile"]).read_text(encoding="utf-8").strip()
    token = base64.b64encode(f"{state['adminId']}:{password}".encode()).decode()
    request = Request(state["serverUrl"] + path,
                      headers={"Authorization": f"Basic {token}"})
    with urlopen(request, timeout=timeout) as response:
        return response.read(64 * 1024 * 1024)


def wait_controller(state: dict, seconds: int = 120) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = json.loads(authenticated_request(state, "/api/json", timeout=5))
            if isinstance(value, dict) and value.get("mode") is not None:
                return
        except (HTTPError, URLError, OSError, json.JSONDecodeError):
            pass
        time.sleep(1)
    fail("Jenkins controller did not become ready")


def agent(arguments: argparse.Namespace) -> int:
    state = read_state(arguments)
    wait_controller(state)
    jar = Path(state["agentRoot"]) / "agent.jar"
    jar.write_bytes(authenticated_request(state, "/jnlpJars/agent.jar"))
    jnlp = authenticated_request(
        state, f"/computer/{NODE_NAME}/jenkins-agent.jnlp").decode("utf-8")
    root = ET.fromstring(jnlp)
    values = [item.text or "" for item in root.findall(".//argument")]
    if len(values) < 2 or not values[0]:
        fail("Jenkins did not return an inbound-agent secret")
    secret_file = Path(state["agentRoot"]) / "secret"
    secure_write(secret_file, values[0] + "\n")
    command = [state["java"], "-jar", str(jar), "-url", state["serverUrl"],
               "-secret", "@" + str(secret_file), "-name", NODE_NAME, "-webSocket",
               "-workDir", state["agentRoot"]]
    return subprocess.run(command, check=False).returncode


def status(arguments: argparse.Namespace) -> int:
    state = read_state(arguments)
    try:
        wait_controller(state, seconds=5)
        node = json.loads(authenticated_request(
            state, f"/computer/{NODE_NAME}/api/json", timeout=5))
    except (RuntimeError, HTTPError, URLError, OSError, json.JSONDecodeError):
        print("controller=offline agent=unknown")
        return 1
    online = isinstance(node, dict) and node.get("offline") is False
    print(f"controller=online agent={'online' if online else 'offline'}")
    return 0 if online else 2


def systemd_quote(value: object) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def android_sdk_root() -> Path | None:
    candidates = (
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
        str(Path.home() / "Android/Sdk"),
    )
    for value in candidates:
        if not value:
            continue
        candidate = Path(value).expanduser().resolve()
        if candidate.is_dir() and (candidate / "platform-tools/adb").is_file():
            return candidate
    return None


def install_systemd_user_services(arguments: argparse.Namespace) -> int:
    if platform.system() != "Linux":
        fail("systemd user services are supported only on Linux")
    state = read_state(arguments)
    unit_root = secure_directory(Path.home() / ".config/systemd/user")
    script = Path(__file__).resolve()
    python = Path(sys.executable).resolve()
    config = Path(arguments.config_root).expanduser().resolve()
    controller_command = " ".join(map(systemd_quote, (
        python, script, "controller", "--config-root", config)))
    agent_command = " ".join(map(systemd_quote, (
        python, script, "agent", "--config-root", config)))
    controller_unit = f"""[Unit]
Description=Overte local Jenkins device-lab controller
After=network-online.target

[Service]
Type=simple
ExecStart={controller_command}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""
    agent_unit = f"""[Unit]
Description=Overte interactive Jenkins physical-device agent
After=overte-jenkins-controller.service graphical-session.target
Wants=overte-jenkins-controller.service
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={agent_command}
Restart=on-failure
RestartSec=5
PassEnvironment=DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_SESSION_TYPE DBUS_SESSION_BUS_ADDRESS
Environment=APPIUM_HOME={systemd_quote(state['appiumHome'])}
EnvironmentFile=-{str(config / 'agent.env')}

[Install]
WantedBy=graphical-session.target
"""
    secure_write(unit_root / "overte-jenkins-controller.service", controller_unit)
    secure_write(unit_root / "overte-jenkins-agent.service", agent_unit)
    appium_unit = None
    if state.get("appiumExecutable"):
        appium_command = " ".join(map(systemd_quote, (
            state["appiumExecutable"], "--address", "127.0.0.1", "--port", "4723")))
        appium_environment = [
            f"Environment={systemd_quote('APPIUM_HOME=' + state['appiumHome'])}",
        ]
        android_sdk = android_sdk_root()
        if android_sdk is not None:
            appium_environment += [
                f"Environment={systemd_quote(f'ANDROID_SDK_ROOT={android_sdk}')}",
                f"Environment={systemd_quote(f'ANDROID_HOME={android_sdk}')}",
            ]
        appium_unit = f"""[Unit]
Description=Overte pinned local Appium server
After=network.target

[Service]
Type=simple
ExecStart={appium_command}
Restart=on-failure
RestartSec=5
{chr(10).join(appium_environment)}
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""
        secure_write(unit_root / "overte-appium.service", appium_unit)
    subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=30, check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now",
                    "overte-jenkins-controller.service"], timeout=30, check=True)
    wait_controller(state)
    subprocess.run(["systemctl", "--user", "enable", "--now",
                    "overte-jenkins-agent.service"], timeout=30, check=True)
    if appium_unit is not None:
        subprocess.run(["systemctl", "--user", "enable", "--now",
                        "overte-appium.service"], timeout=30, check=True)
    print("Installed and started the local Jenkins controller and interactive agent.")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config-root", required=True)
    sub = value.add_subparsers(dest="command", required=True)
    install_parser = sub.add_parser("install", parents=[common])
    install_parser.add_argument("--install-root", required=True)
    install_parser.add_argument("--java", required=True)
    install_parser.add_argument("--npm", default="npm")
    install_parser.add_argument("--port", type=int, default=8080)
    install_parser.add_argument("--skip-appium", action="store_true")
    install_parser.set_defaults(function=install)
    for name, function in (("controller", controller), ("agent", agent), ("status", status),
                           ("install-systemd-user-services", install_systemd_user_services)):
        action = sub.add_parser(name, parents=[common])
        action.set_defaults(function=function)
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        return arguments.function(arguments)
    except (RuntimeError, subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
