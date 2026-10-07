#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Select verified lab host executables without changing system services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import time
import stat
import subprocess
import sys

MODULES = ("module-native-protocol-unix.so", "module-null-sink.so")
MAX_PATH = 4096


def checked_path(value, *, executable=False, directory=False):
    text = str(value)
    if not text or len(text) > MAX_PATH or any(character in text for character in "\x00\r\n:"):
        raise RuntimeError("Host tool path is empty, too long, or contains an environment separator")
    path = Path(text)
    if not path.is_absolute():
        raise RuntimeError("Host tool paths must be absolute")
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise RuntimeError("Host tool path does not resolve to an existing file") from error
    if len(str(path)) > MAX_PATH or any(character in str(path) for character in "\r\n:"):
        raise RuntimeError("Resolved host tool path contains an environment separator")
    if directory:
        if not path.is_dir() or path in (Path('/'), Path('/home'), Path('/tmp')):
            raise RuntimeError("Host tool directory is missing or too broad")
    elif not stat.S_ISREG(path.stat().st_mode) or executable and not os.access(path, os.X_OK):
        raise RuntimeError("Host tool is not a regular executable file")
    return path


def module_directory(value):
    path = checked_path(value, directory=True)
    for name in MODULES:
        module = checked_path(path / name)
        if module.parent != path:
            raise RuntimeError("PulseAudio module escapes its configured directory")
    return path


def command_path(name, supplied=None):
    value = supplied or shutil.which(name)
    if not value:
        raise RuntimeError(f"Required host command is missing: {name}")
    return checked_path(value, executable=True)


def discover_modules():
    # A fixed shallow set, never recursive traversal of arbitrary profiles.
    candidates = [Path('/usr/lib/x86_64-linux-gnu/pulseaudio/modules'), Path('/usr/lib64/pulseaudio/modules'), Path('/usr/lib/pulseaudio/modules')]
    versions = sorted(Path('/usr/lib').glob('pulse-*/modules'))
    if len(versions) > 32:
        raise RuntimeError("Too many PulseAudio module candidates; supply --pulse-modules explicitly")
    for candidate in candidates + versions:
        try:
            return module_directory(candidate)
        except RuntimeError:
            pass
    raise RuntimeError("No verified PulseAudio modules found; supply --pulse-modules explicitly")


def select_tools(root, mode='fedora', *, xvfb=None, pulseaudio=None, pulse_modules=None, pulse_libraries=(), slirp=None):
    if mode not in ('fedora', 'system'):
        raise RuntimeError("Unknown host tools mode")
    if mode == 'fedora':
        if any((xvfb, pulseaudio, pulse_modules, pulse_libraries, slirp)):
            raise RuntimeError("Explicit host paths require --host-tools system")
        base = Path(root) / 'host-tools/usr'
        xvfb = base / 'bin/Xvfb'
        pulseaudio = base / 'bin/pulseaudio'
        pulse_modules = base / 'lib64/pulseaudio/modules'
        pulse_libraries = (base / 'lib64', base / 'lib64/pulseaudio', pulse_modules)
        slirp = shutil.which('slirp4netns') or str(base / 'bin/slirp4netns')
    if len(pulse_libraries) > 8:
        raise RuntimeError("At most eight explicit PulseAudio library directories are supported")
    return {'version': 1, 'mode': mode,
            'xvfb': str(command_path('Xvfb', xvfb)), 'pulseaudio': str(command_path('pulseaudio', pulseaudio)),
            'pulseModules': str(module_directory(pulse_modules) if pulse_modules else discover_modules()),
            'pulseLibraries': [str(checked_path(value, directory=True)) for value in pulse_libraries],
            'slirp': str(command_path('slirp4netns', slirp))}


def verify_tools(document):
    if not isinstance(document, dict) or type(document.get('version')) is not int or document.get('version') != 1 or document.get('mode') not in ('fedora', 'system'):
        raise RuntimeError("Invalid host-tools configuration")
    libraries = document.get('pulseLibraries')
    if not isinstance(libraries, list) or len(libraries) > 8:
        raise RuntimeError("Invalid PulseAudio library directories")
    verified = {'version': 1, 'mode': document['mode'],
                'xvfb': str(checked_path(document.get('xvfb', ''), executable=True)),
                'pulseaudio': str(checked_path(document.get('pulseaudio', ''), executable=True)),
                'pulseModules': str(module_directory(document.get('pulseModules', ''))),
                'pulseLibraries': [str(checked_path(value, directory=True)) for value in libraries],
                'slirp': str(checked_path(document.get('slirp', ''), executable=True))}
    return verified


def load_tools(root):
    config = Path(root) / 'config/host-tools.json'
    if config.exists():
        if config.stat().st_size > 65536:
            raise RuntimeError("Host-tools configuration is too large")
        return verify_tools(json.loads(config.read_text()))
    return select_tools(root)


def pulse_environment(tools, environment=None):
    environment = dict(os.environ if environment is None else environment)
    # Native Qt/AppImage libraries must never contaminate a host audio process.
    environment.pop('LD_LIBRARY_PATH', None)
    if tools['pulseLibraries']:
        environment['LD_LIBRARY_PATH'] = ':'.join(tools['pulseLibraries'])
    return environment


def pulse_arguments(tools, arguments):
    arguments = [str(value) for value in arguments]
    if any(value == '--dl-search-path' or value.startswith('--dl-search-path=') for value in arguments):
        raise RuntimeError("PulseAudio module path is supplied by the verified host-tools configuration")
    return [tools['pulseaudio'], '--dl-search-path=' + tools['pulseModules'], *arguments]


def bounded_command(arguments, *, environment=None, timeout=10):
    # Trusted host commands only, bounded wall time and an on-disk output cap.
    import tempfile
    environment = dict(os.environ if environment is None else environment)
    environment['LC_ALL'] = 'C'
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(value) for value in arguments], env=environment, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if os.fstat(output.fileno()).st_size > 65536:
                    raise RuntimeError("Host preflight command produced excessive output")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Host preflight command exceeded its deadline")
                time.sleep(0.02)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        output.seek(0)
        result = output.read(65537)
    if len(result) > 65536:
        raise RuntimeError("Host preflight command produced excessive output")
    if process.returncode != 0:
        raise RuntimeError("Host preflight command failed; dependencies or namespaces are unavailable")
    return result.decode('utf-8', errors='replace')




def tool_identities(tools):
    """Portable byte identities; do not publish operator installation paths."""
    files = {name: Path(tools[name]) for name in ['xvfb', 'pulseaudio', 'slirp']}
    files.update({name: Path(tools['pulseModules']) / name for name in MODULES})
    result = {}
    for role, path in files.items():
        path = checked_path(path)
        if path.stat().st_size > 256 * 1024 * 1024:
            raise RuntimeError('Host tool exceeds the reviewed identity scan limit')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        result[role] = {'filename': path.name, 'sha256': digest}
    return {'version': 1, 'mode': tools['mode'], 'tools': result}

def preflight(root, tools):
    """Actual local dependency/isolation/audio checks; no domain or user profile."""
    import tempfile
    tools = verify_tools(tools)
    commands = {name: command_path(name) for name in ['ldd', 'ffmpeg', 'pactl', 'rpm2cpio', 'cpio', 'ar', 'tar', 'bwrap', 'xauth', 'ip', 'unshare', 'g++', 'true']}
    # Test actual kernel availability. Never skip or globally relax a policy.
    bounded_command([commands['unshare'], '--user', '--map-current-user', '--ipc', '--pid', '--fork', '--mount-proc', '--net', '--', commands['true']])
    sandbox = [commands['bwrap'], '--unshare-user', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--die-with-parent']
    for directory in ['/usr', '/bin', '/lib', '/lib64']:
        if Path(directory).is_dir():
            sandbox.extend(['--ro-bind', directory, directory])
    bounded_command([*sandbox, '--proc', '/proc', '--dev', '/dev', '--', commands['true']])
    root = Path(root)
    app = root / 'appimage/squashfs-root'
    qt = root / 'qt-tablet/usr/lib/x86_64-linux-gnu'
    native_env = dict(os.environ, LD_LIBRARY_PATH=f'{root / "server/opt/overte/lib"}:{app / "usr/lib"}:{qt}')
    pulse_env = pulse_environment(tools)
    dependencies = [(tools['xvfb'], dict(os.environ)), (tools['pulseaudio'], pulse_env)]
    dependencies.extend((str(Path(tools['pulseModules']) / name), pulse_env) for name in MODULES)
    dependencies.extend((path, native_env) for path in [root / 'server/opt/overte/domain-server', root / 'server/opt/overte/assignment-client',
        app / 'usr/bin/interface', app / 'usr/plugins/platforms/libqxcb.so', qt / 'qt5/qml/QtTest/libqmltestplugin.so',
        root / 'native-input/qml/BrowserNativeInput/libbrowsernativeinput.so'])
    for binary, environment in dependencies:
        binary = checked_path(binary)
        with binary.open('rb') as stream:
            header = stream.read(4)
        if header != b'\x7fELF':
            raise RuntimeError('A required native preflight target is not an ELF binary')
        listing = bounded_command([commands['ldd'], binary], environment=environment)
        if 'not found' in listing:
            raise RuntimeError(f'Native dependency closure is incomplete: {binary.name}')
    media_env = dict(os.environ)
    media_env.pop('LD_LIBRARY_PATH', None)
    devices = bounded_command([commands['ffmpeg'], '-hide_banner', '-devices'], environment=media_env)
    for device in ['pulse', 'x11grab']:
        if not any(len(parts := line.split()) >= 2 and 'D' in parts[0] and parts[1] == device for line in devices.splitlines()):
            raise RuntimeError(f'FFmpeg lacks the required input device: {device}')
    version = bounded_command([tools['pulseaudio'], '--version'], environment=pulse_env).strip()
    # Verify module ABI by loading only private null sinks. Neither a host audio
    # daemon nor a physical device is selected, changed, or enumerated.
    with tempfile.TemporaryDirectory(prefix='overte-host-audio-') as temporary:
        directory = Path(temporary)
        script = directory / 'preflight.pa'
        address = 'unix:' + str(directory / 'pulse.sock')
        script.write_text(f'load-module module-native-protocol-unix socket={directory / "pulse.sock"} auth-anonymous=1\n'
                          'load-module module-null-sink sink_name=preflight_input rate=48000 channels=1\n'
                          'load-module module-null-sink sink_name=preflight_output rate=48000 channels=2\n'
                          'set-default-source preflight_input.monitor\nset-default-sink preflight_output\n')
        environment = dict(pulse_env, PULSE_SERVER=address, XDG_RUNTIME_DIR=temporary, XDG_CONFIG_HOME=str(directory / 'config'),
                           XDG_CACHE_HOME=str(directory / 'cache'), XDG_DATA_HOME=str(directory / 'data'),
                           PULSE_RUNTIME_PATH=temporary, PULSE_STATE_PATH=str(directory / 'state'),
                           PULSE_COOKIE=str(directory / 'cookie'), DBUS_SESSION_BUS_ADDRESS='unix:path=/dev/null')
        for name in ['PULSE_SOURCE', 'PULSE_SINK']:
            environment.pop(name, None)
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(pulse_arguments(tools, ['-n', '--daemonize=no', '--use-pid-file=no', '--exit-idle-time=-1', '-F', script]),
                                       env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 10
                while not (directory / 'pulse.sock').exists():
                    if process.poll() is not None or time.monotonic() >= deadline or os.fstat(log.fileno()).st_size > 65536:
                        raise RuntimeError('Private PulseAudio module/ABI preflight did not become ready')
                    time.sleep(.05)
                client_env = dict(media_env, PULSE_SERVER=address)
                source = bounded_command([commands['pactl'], '--server=' + address, 'get-default-source'], environment=client_env)
                sink = bounded_command([commands['pactl'], '--server=' + address, 'get-default-sink'], environment=client_env)
                if source.strip() != 'preflight_input.monitor' or sink.strip() != 'preflight_output':
                    raise RuntimeError('Private audio preflight did not retain the configured null-only defaults')
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
    return {'hostToolsMode': tools['mode'], 'pulseAudioVersion': version, 'elfDependencyTargets': len(dependencies),
            'kernelNamespaces': 'passed', 'bubblewrapNamespaces': 'passed', 'privatePulseModules': 'passed',
            'physicalAudioDevices': 'not-used', 'nativeGuiAndDomainJourney': 'not-tested-by-preflight'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['exec-pulse'])
    parser.add_argument('--root', required=True, type=Path)
    args, arguments = parser.parse_known_args()
    tools = load_tools(args.root)
    arguments = arguments[1:] if arguments[:1] == ['--'] else arguments
    if arguments not in (['--version'], ['--help']):
        required = {'-n', '--daemonize=no', '--use-pid-file=no'}
        if not required.issubset(arguments) or '-F' not in arguments or any(value in arguments for value in ['--start', '--kill', '-k']):
            raise RuntimeError('The lab audio launcher requires explicit isolated startup flags; desktop daemon actions are refused')
    os.execve(tools['pulseaudio'], pulse_arguments(tools, arguments), pulse_environment(tools))


if __name__ == '__main__':
    main()
