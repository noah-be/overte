"""Finite CPU historical inputs only; never imported by launch or stop."""
import hashlib
import json
import os
from pathlib import Path
import stat
import zlib

PINS = {'browser-client/lab/manage.py': {'before': '84b4426187e078515b77984a3581a63130d2dbc0c5edf4230a66a17ecdbf8e66', 'after': '53cd7fcce5887c993bc724ce3e391c4c7d0975f338ed1c96a1adfdbe7c9bdb95'}, 'browser-client/lab/test_manage_state.py': {'before': 'e47cfdf2410db2f325a6f6087109366f54f685ca5e799282b6e8e343f068e1eb', 'after': '103ee00b456fefeb262b5cce7a4b9738dab219077bb4d62aa5b1cf3a102c46c2'}, 'browser-client/lab/atomic-provisioning/source-pins.json': {'before': '7b54a00eb198b88db7981dffaabad74b4144cc0f188aefd9f5214e9afba61a38', 'after': '709fafd17508b5a275a82a78f13f58f57b07686746c2cc453635d4a70db808b9'}, 'browser-client/lab/atomic-provisioning/test_managed_composition.py': {'before': '4f927e11c9d297bb2fcebe835ac765fa3045a27ebaa0eb24187f8e34594fe1fd', 'after': '31c587e7ba721c3d6e083a77daa7ab5c70591b56b019b5283aefd61abbb63fb3'}, 'browser-client/lab/atomic-provisioning/fixtures/managed-seven-manage-recovery.json': {'before': '3475eb21c4ad7617c465241acd65940edce5db8d325056efc26993d56e831d18', 'after': 'e471f11465d9575c316decd0c6e9d91c5200d05de6531474c590993501e79109'}}
ARCHIVE_SHA256 = '5b1870bc3583da9bca904e1c76fdd900f11ee02f569eb9a7b93395b8b1b9302c'
ARCHIVE = Path(__file__).resolve().parent / 'fixtures/managed-ancestry-before.json.gz'


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('managed-ancestry-history-duplicate')
        result[key] = value
    return result


def checked_archive(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 131072:
        raise ValueError('managed-ancestry-history-bound')
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('managed-ancestry-history-archive')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    text = decoder.decompress(raw, 524289)
    if len(text) > 524288 or decoder.unconsumed_tail or decoder.unused_data or not decoder.eof:
        raise ValueError('managed-ancestry-history-bound')
    document = json.loads(text, object_pairs_hook=unique)
    if type(document) is not dict or set(document) != {'schemaVersion', 'sources'} or type(document['schemaVersion']) is not int or document['schemaVersion'] != 1:
        raise ValueError('managed-ancestry-history-schema')
    sources = document['sources']
    if type(sources) is not dict or set(sources) != set(PINS):
        raise ValueError('managed-ancestry-history-members')
    for path, pin in PINS.items():
        row = sources[path]
        if type(row) is not dict or set(row) != {'beforeText', 'beforeSHA256', 'afterSHA256'} or type(row['beforeText']) is not str or row['beforeSHA256'] != pin['before'] or row['afterSHA256'] != pin['after'] or hashlib.sha256(row['beforeText'].encode()).hexdigest() != pin['before']:
            raise ValueError('managed-ancestry-history-source')
    return sources


def read_archive():
    if ARCHIVE.resolve(strict=True) != ARCHIVE:
        raise ValueError('managed-ancestry-history-path')
    fd = os.open(ARCHIVE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1 or before.st_mode & 0o022 or not 0 < before.st_size <= 131072:
            raise ValueError('managed-ancestry-history-file')
        raw = os.read(fd, 131073)
        after = os.fstat(fd)
        if len(raw) != before.st_size or any(getattr(before, key) != getattr(after, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
            raise ValueError('managed-ancestry-history-file')
        return checked_archive(raw)
    finally:
        os.close(fd)


def recover(path, current):
    if path not in PINS or type(current) is not bytes or len(current) > 262144 or hashlib.sha256(current).hexdigest() != PINS[path]['after']:
        raise ValueError('managed-ancestry-history-current')
    return read_archive()[path]['beforeText'].encode()
