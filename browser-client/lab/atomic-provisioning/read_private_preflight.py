# SPDX-License-Identifier: Apache-2.0
"""Project only fixed categories from an already retained ORIGINAL invocation."""
import argparse
import json
import os
import re
import stat
from preflight_diagnostics import MAX_BYTES, stderr_failure


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def project_retained(cache, capture):
    result = {'scope': 'original-retained-private-preflight-prefix', 'status': 'read-refused',
              'stderrBytes': 0, 'stderrFailure': 'unobserved-or-unclassified'}
    parent = child = fd = None
    try:
        if type(cache) is not str or type(capture) is not str or not re.fullmatch(r'preflight-failure-[a-f0-9]{16}', capture):
            raise ValueError('private-capture-input-refused')
        parent = os.open(cache, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for selected in ('parent', 'child'):
            if selected == 'child':
                child = os.open(capture, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            info = os.fstat(parent if selected == 'parent' else child)
            if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError('private-directory-refused')
        fd = os.open('stderr-prefix.private.log', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=child)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600 or not 0 <= before.st_size <= MAX_BYTES:
            raise ValueError('private-prefix-refused')
        data = bytearray()
        while len(data) <= MAX_BYTES:
            part = os.read(fd, min(1024, MAX_BYTES + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        if len(data) != before.st_size or len(data) > MAX_BYTES or identity(before) != identity(os.fstat(fd)):
            raise ValueError('private-prefix-changed')
        result.update(status='read-verified-private', stderrBytes=len(data), stderrFailure=stderr_failure(bytes(data)))
    except (OSError, ValueError, TypeError):
        pass
    finally:
        for selected in (fd, child, parent):
            if selected is not None:
                os.close(selected)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', required=True)
    parser.add_argument('--capture', required=True)
    args = parser.parse_args()
    result = project_retained(args.cache, args.capture)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    raise SystemExit(0 if result['status'] == 'read-verified-private' else 1)
