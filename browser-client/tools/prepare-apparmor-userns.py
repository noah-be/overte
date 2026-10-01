#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reload only absent, unmodified distro namespace profiles on an ephemeral runner.

Install apparmor-profiles through the runner's normal signed apt repositories
before invoking this helper as root. The exact root-owned /usr/share directory
is tightened if the ephemeral image made it group/other writable. No replacement
policy is generated here.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

TARGETS = (
    ('bwrap-userns-restrict', 'apparmor-profiles', 'bwrap', '/usr/bin/bwrap'),
    ('unshare-userns-restrict', 'apparmor-profiles', 'unshare', '/usr/bin/unshare'),
)
ALLOWED_NAMES = {'bwrap', 'unshare', 'unpriv_bwrap', 'unshare//unpriv'}
PROFILE_PARENT = Path('/usr/share')
PROFILE_DIRECTORY = Path('/usr/share/apparmor/extra-profiles')
PACKAGE_MANIFEST = Path('/var/lib/dpkg/info/apparmor-profiles.md5sums')


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
    for parent in path.parents:
        try:
            parent_info = parent.stat()
            parent_canonical = parent.resolve(strict=True)
        except OSError as error:
            raise PolicyError('required-distro-directory-unavailable') from error
        if parent_canonical != parent or not stat.S_ISDIR(parent_info.st_mode) \
                or parent_info.st_uid != 0 or parent_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PolicyError('distro-parent-directory-owner-or-write-permissions-invalid')
    return info


def harden_profile_parent():
    """Remove only unsafe write bits on the fixed ephemeral distro directory.

    No caller-supplied path, package/profile substitution, or policy relaxation
    is accepted. Hold a no-follow directory descriptor through chmod and verify
    its pathname identity before and after. The existing file/package checks
    still run afterward; a later refusal does not restore unsafe write access.
    """
    if os.geteuid() != 0:
        raise PolicyError('root-required-for-distro-directory-hardening')
    path = PROFILE_PARENT
    for ancestor in path.parents:
        info = ancestor.stat()
        if ancestor.resolve(strict=True) != ancestor or not stat.S_ISDIR(info.st_mode) \
                or info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PolicyError('distro-directory-ancestor-is-not-trusted')
    if path.resolve(strict=True) != path:
        raise PolicyError('distro-directory-is-not-canonical')
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        current = path.stat(follow_symlinks=False)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0:
            raise PolicyError('distro-directory-is-not-root-owned-directory')
        if identity != (current.st_dev, current.st_ino) or path.resolve(strict=True) != path:
            raise PolicyError('distro-directory-identity-changed')
        before = stat.S_IMODE(info.st_mode)
        after = before & ~(stat.S_IWGRP | stat.S_IWOTH)
        if after != before:
            os.fchmod(descriptor, after)
        verified = os.fstat(descriptor)
        current = path.stat(follow_symlinks=False)
        if identity != (current.st_dev, current.st_ino) or path.resolve(strict=True) != path \
                or verified.st_uid != 0 or stat.S_IMODE(verified.st_mode) != after:
            raise PolicyError('distro-directory-hardening-not-verified')
        return {'path': str(path), 'beforeMode': f'{before:04o}', 'afterMode': f'{after:04o}',
                'action': 'removed-group-other-write' if before != after else 'preserved-secure-mode'}
    finally:
        os.close(descriptor)


def package_file_digest(path):
    """Use dpkg's exact package-file manifest after normal signed apt install."""
    trusted_file(PACKAGE_MANIFEST)
    document = PACKAGE_MANIFEST.read_text()
    if len(document) > 1024 * 1024:
        raise PolicyError('distro-package-manifest-size-limit')
    relative = str(path).removeprefix('/')
    matches = re.findall(r'^([a-f0-9]{32})  ' + re.escape(relative) + r'$', document, re.M)
    if len(matches) != 1:
        raise PolicyError('distro-profile-missing-or-ambiguous-in-package-manifest')
    return matches[0]


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
    path = PROFILE_DIRECTORY / filename
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
    # Noble ships these disabled-by-default extra profiles as ordinary package
    # files, not conffiles. MD5 is only the package compatibility checksum; root
    # ownership and the signed apt installation remain the trust boundary.
    if hashlib.md5(content, usedforsecurity=False).hexdigest() != package_file_digest(path):
        raise PolicyError('distro-profile-differs-from-recorded-package-file')
    text = content.decode('utf-8')
    if not re.search(r'^\s*abi\s+<abi/4\.0>\s*,\s*$', text, re.M):
        raise PolicyError('distro-profile-abi-not-reviewed')
    if not re.search(r'^\s*profile\s+' + re.escape(profile) + r'\s', text, re.M):
        raise PolicyError('distro-main-profile-name-not-reviewed')
    return {'filename': filename, 'package': package, 'profile': profile,
            'sha256': hashlib.sha256(content).hexdigest(), 'packageFileUnmodified': True,
            'path': str(path)}


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
    directory_hardening = harden_profile_parent()
    before = loaded_profiles()
    # Validate *all* targets before mutating either. Never replace a loaded
    # profile: it might intentionally enforce stronger runtime policy.
    targets = [inspect_target(*target) for target in TARGETS]
    for target in targets:
        if target['profile'] in before:
            target['action'] = 'preserved-existing-loaded-profile'
            continue
        # Parse the checked source rather than an unrelated cached policy. Use
        # the distro include base; do not replace any existing policy.
        command([str(parser), '-a', '-K', '-b', '/etc/apparmor.d',
                 str(PROFILE_DIRECTORY / target['filename'])])
        after_load = loaded_profiles()
        if target['profile'] not in after_load:
            raise PolicyError('shipped-main-profile-remained-unloaded')
        target['action'] = 'loaded-unchanged-package-profile'
    return {'passed': True, 'scope': 'Ephemeral runner exact signed-package namespace profile preparation',
            'policyReplacement': 'none', 'before': before, 'after': loaded_profiles(),
            'targets': targets, 'directoryHardening': directory_hardening, 'normalSandboxAndNativePreflight': 'still-required'}


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
