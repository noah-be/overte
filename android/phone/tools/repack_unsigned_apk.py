#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recompress an unsigned APK losslessly, then restore and verify 16 KiB alignment."""
import argparse
import copy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import zipfile


def inventory(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate APK paths')
        with Path(path).open('rb') as stream:
            stream.seek(max(0, archive.start_dir - 16))
            if stream.read(16) == b'APK Sig Block 42':
                raise ValueError('refusing an APK with a signing block')
        result = {}
        for entry in archive.infolist():
            upper = entry.filename.upper()
            if upper.startswith('META-INF/') and upper.endswith(('.SF', '.RSA', '.DSA', '.EC')):
                raise ValueError('refusing a signed APK')
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError('unsupported APK compression method')
            result[entry.filename] = (hashlib.sha256(archive.read(entry)).hexdigest(),
                                      entry.compress_type, entry.date_time, entry.external_attr)
        return result


def recompress(source, output):
    before = inventory(source)
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output, 'w', compresslevel=9) as target:
        target.comment = original.comment
        for entry in original.infolist():
            info = copy.copy(entry)
            target.writestr(info, original.read(entry), compress_type=entry.compress_type,
                            compresslevel=9 if entry.compress_type == zipfile.ZIP_DEFLATED else None)
            # ZipFile substitutes a default permission when the original is zero.
            # Restore the original central-directory metadata before close().
            info.external_attr = entry.external_attr
    if inventory(output) != before:
        raise ValueError('APK entries changed during recompression')


def optimize(apk, zipalign):
    before = inventory(apk)
    old_size = apk.stat().st_size
    with tempfile.TemporaryDirectory(prefix='phone-repack-', dir=apk.parent) as directory:
        raw, aligned = (Path(directory)/name for name in ('raw.apk', 'aligned.apk'))
        recompress(apk, raw)
        subprocess.run([str(zipalign), '-f', '-P', '16', '4', str(raw), str(aligned)], check=True)
        subprocess.run([str(zipalign), '-c', '-P', '16', '4', str(aligned)], check=True)
        if inventory(aligned) != before:
            raise ValueError('APK entries changed during alignment')
        if aligned.stat().st_size < old_size:
            aligned.replace(apk)
    print(f'Lossless APK packaging: {old_size} -> {apk.stat().st_size} bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--zipalign', type=Path, required=True)
    args = parser.parse_args()
    optimize(args.apk, args.zipalign)
