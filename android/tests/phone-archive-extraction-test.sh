#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_file="$script_dir/../../interface/src/ArchiveDownloadInterface.cpp"

require() {
    local pattern="$1" description="$2"
    grep -Eq -- "$pattern" "$source_file" || {
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    }
}

reject() {
    local pattern="$1" description="$2"
    ! grep -Eq -- "$pattern" "$source_file" || {
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    }
}

require '^#include <quazip/quazip[.]h>' 'QuaZip must be available to the Android build'
require 'extractArchiveSafely' 'archive extraction must use the validated entry point'
require 'QFile archiveFile.*archivePath' 'validation and extraction must share one archive handle'
require 'archiveFile[.]open\(QIODevice::ReadOnly\)' 'the archive handle must remain read-only'
require 'QDir::isAbsolutePath' 'absolute archive paths must be rejected'
require 'cleanPath != path' 'non-canonical archive paths must be rejected'
require 'path[.]contains' 'backslash paths must be rejected'
require 'info[.]isSymbolicLink' 'archive symbolic links must be rejected'
require 'paths[.]contains' 'duplicate archive paths must be rejected'
require 'MAX_ARCHIVE_ENTRIES = 4096' 'archive entry count must be bounded'
require 'MAX_ARCHIVE_FILE_BYTES = 256LL' 'individual expansion size must be bounded'
require 'MAX_ARCHIVE_TOTAL_BYTES = 512LL' 'aggregate expansion size must be bounded'
require 'MAX_ARCHIVE_PATH_BYTES = 1024' 'archive path length must be bounded'
require 'QDir\(target\)[.]removeRecursively' 'failed extraction must remove partial output'
reject 'defined\(Q_OS_ANDROID\).*return QStringList' \
    'Android extraction must not retain the obsolete empty-result stub'

printf 'Phone safe archive extraction contracts passed.\n'
