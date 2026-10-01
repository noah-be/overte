#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reload only absent, unmodified distro namespace profiles on an ephemeral runner.

Install apparmor-profiles through the runner's normal signed apt repositories
before invoking this helper as root. No replacement policy is generated here.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

TARGETS = (
    ('bwrap-userns-restrict', 'apparmor', 'bwrap', '/usr/bin/bwrap'),
    ('unshare-userns-restrict', 'apparmor-profiles', 'unshare', '/usr/bin/unshare'),
)
ALLOWED_NAMES = {'bwrap', 'unshare', 'unpriv_bwrap', 'unpriv_unshare'}


class PolicyError(RuntimeError):
    pass


def command(arguments):
    if arguments[0] == 'dpkg-query':
        arguments = ['/usr/bin/dpkg-query', *arguments[1:]]
    try:
        result = subprocess.run(arguments, capture_output=True, text=True,
                                timeout=15, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PolicyError('package-or-parser-command-unavailable') from error
    if len(result.stdout) > 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        raise PolicyError('package-or-parser-output-limit')
    if result.returncode:
        raise PolicyError('package-or-parser-command-failed')
    return result.stdout


def trusted_file(path):
    """Reject aliases and writable substitutes for the exact distro attachment."""
    try:
        canonical = path.resolve(strict=True)
        info = path.stat()
    except OSError as error:
        raise PolicyError('required-distro-file-unavailable') from error
    if canonical != path or not stat.S_ISREG(info.st_mode):
        raise PolicyError('distro-file-is-not-canonical-regular-file')
    if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PolicyError('distro-file-owner-or-write-permissions-invalid')
    return info


def loaded_profiles():
    try:
        text = Path('/sys/kernel/security/apparmor/profiles').read_text()
    except OSError as error:
        raise PolicyError('active-apparmor-profile-list-unavailable') from error
    if len(text) > 1024 * 1024:
        raise PolicyError('active-apparmor-profile-list-limit')
    return {name: mode for name, mode in re.findall(r'^([^\n]+) \(([^\n]+)\)$', text, re.M)
            if name in ALLOWED_NAMES}


def package_owns_exact_executable(path, package):
    # usr-merged dpkg metadata can retain the legacy /bin or /sbin pathname.
    # Accept only that exact known alias when it resolves to this same canonical
    # executable; never accept an arbitrary path or broad directory owner.
    paths = [path]
    if str(path).startswith('/usr/bin/'):
        paths.append(Path('/bin') / path.name)
    elif str(path).startswith('/usr/sbin/'):
        paths.append(Path('/sbin') / path.name)
    for candidate in paths:
        if candidate.resolve(strict=True) != path:
            continue
        try:
            owner = command(['dpkg-query', '--search', str(candidate)]).splitlines()
        except PolicyError:
            continue
        if owner == [f'{package}: {candidate}']:
            return True
    return False


def inspect_target(filename, package, profile, executable):
    path = Path('/etc/apparmor.d') / filename
    trusted_file(path)
    executable_path = Path(executable)
    info = trusted_file(executable_path)
    if not info.st_mode & stat.S_IXUSR:
        raise PolicyError('distro-executable-is-not-executable')
    if os.path.lexists(Path('/etc/apparmor.d/disable') / filename):
        raise PolicyError('distro-profile-disabled-by-operator')
    if command(['dpkg-query', '--show', '--showformat=${db:Status-Status}', package]).strip() != 'installed':
        raise PolicyError('required-distro-profile-package-not-installed')
    owner = command(['dpkg-query', '--search', str(path)]).splitlines()
    if owner != [f'{package}: {path}']:
        raise PolicyError('profile-is-not-owned-by-expected-package')
    expected_binary_package = 'bubblewrap' if profile == 'bwrap' else 'util-linux'
    if not package_owns_exact_executable(executable_path, expected_binary_package):
        raise PolicyError('executable-is-not-owned-by-expected-package')
    content = path.read_bytes()
    if len(content) > 256 * 1024:
        raise PolicyError('distro-profile-size-limit')
    conffiles = command(['dpkg-query', '--show', '--showformat=${Conffiles}', package])
    match = re.search(r'^[ \t]*' + re.escape(str(path)) + r'[ \t]+([a-f0-9]{32})[ \t]*$', conffiles, re.M)
    # dpkg records conffile checksums with MD5. This checks unmodified package
    # configuration after signed apt installation, not password authentication.
    if not match or hashlib.md5(content, usedforsecurity=False).hexdigest() != match.group(1):
        raise PolicyError('distro-profile-differs-from-recorded-package-conffile')
    text = content.decode('utf-8')
    if not re.search(r'^\s*abi\s+<abi/4\.0>\s*,\s*$', text, re.M):
        raise PolicyError('distro-profile-abi-not-reviewed')
    if not re.search(r'^\s*profile\s+' + re.escape(profile) + r'\s', text, re.M):
        raise PolicyError('distro-main-profile-name-not-reviewed')
    return {'filename': filename, 'package': package, 'profile': profile,
            'sha256': hashlib.sha256(content).hexdigest(), 'packageConffileUnmodified': True}


def prepare():
    if os.geteuid() != 0:
        raise PolicyError('root-required-for-targeted-distro-profile-reload')
    trusted_file(Path('/usr/bin/dpkg-query'))
    parser = Path('/sbin/apparmor_parser')
    # On usr-merged Ubuntu /sbin is an alias; the parser itself must resolve to
    # the root-owned distro executable, not a workspace-provided substitute.
    parser = parser.resolve(strict=True)
    if parser != Path('/usr/sbin/apparmor_parser'):
        raise PolicyError('distro-parser-path-not-reviewed')
    if not trusted_file(parser).st_mode & stat.S_IXUSR:
        raise PolicyError('distro-parser-is-not-executable')
    if not package_owns_exact_executable(parser, 'apparmor'):
        raise PolicyError('parser-is-not-owned-by-apparmor-package')
    before = loaded_profiles()
    # Validate *all* targets before mutating either. Never replace a loaded
    # profile: it might intentionally enforce stronger runtime policy.
    targets = [inspect_target(*target) for target in TARGETS]
    for target in targets:
        if target['profile'] in before:
            target['action'] = 'preserved-existing-loaded-profile'
            continue
        command([str(parser), '-a', str(Path('/etc/apparmor.d') / target['filename'])])
        after_load = loaded_profiles()
        if target['profile'] not in after_load:
            raise PolicyError('shipped-main-profile-remained-unloaded')
        target['action'] = 'loaded-unchanged-package-profile'
    return {'passed': True, 'scope': 'Ephemeral runner exact signed-package namespace profile preparation',
            'policyReplacement': 'none', 'before': before, 'after': loaded_profiles(),
            'targets': targets, 'normalSandboxAndNativePreflight': 'still-required'}


def main():
    try:
        report = prepare()
        code = 0
    except (PolicyError, OSError, UnicodeError) as error:
        report = {'passed': False, 'category': str(error) if isinstance(error, PolicyError)
                  else 'distro-policy-inspection-os-or-format-error', 'policyReplacement': 'none'}
        code = 1
    print(json.dumps(report, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
