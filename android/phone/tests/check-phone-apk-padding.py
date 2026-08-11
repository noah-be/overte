#!/usr/bin/env python3

import argparse
import struct
import sys
import zipfile


MAX_PADDING_BYTES = 64 * 1024
LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
END_OF_CENTRAL_DIRECTORY = struct.Struct("<4sHHHHIIH")


def entry_data_end(apk_file, entry):
    apk_file.seek(entry.header_offset)
    header = apk_file.read(LOCAL_HEADER.size)
    if len(header) != LOCAL_HEADER.size:
        raise ValueError(f"truncated local header for {entry.filename}")
    fields = LOCAL_HEADER.unpack(header)
    if fields[0] != 0x04034B50:
        raise ValueError(f"invalid local header for {entry.filename}")
    name_length, extra_length = fields[-2:]
    return entry.header_offset + LOCAL_HEADER.size + name_length + extra_length + entry.compress_size


def largest_internal_gap(apk_path):
    with zipfile.ZipFile(apk_path) as archive, open(apk_path, "rb") as apk_file:
        entries = sorted(archive.infolist(), key=lambda entry: entry.header_offset)
        largest_gap = 0
        previous_end = 0
        previous_name = "start of archive"
        largest_location = ""
        for entry in entries:
            gap = entry.header_offset - previous_end
            if gap > largest_gap:
                largest_gap = gap
                largest_location = f"after {previous_name}, before {entry.filename}"
            previous_end = max(previous_end, entry_data_end(apk_file, entry))
            previous_name = entry.filename
        central_directory_gap = archive.start_dir - previous_end
        if central_directory_gap > largest_gap:
            largest_gap = central_directory_gap
            largest_location = f"after {previous_name}, before the central directory"
        return largest_gap, largest_location


def trailing_data_size(apk_path):
    with zipfile.ZipFile(apk_path) as archive, open(apk_path, "rb") as apk_file:
        apk_file.seek(0, 2)
        file_size = apk_file.tell()
        search_size = min(file_size, END_OF_CENTRAL_DIRECTORY.size + 65535)
        apk_file.seek(file_size - search_size)
        tail = apk_file.read(search_size)
        signature = b"PK\x05\x06"
        candidate = tail.rfind(signature)
        while candidate >= 0:
            if candidate + END_OF_CENTRAL_DIRECTORY.size <= len(tail):
                fields = END_OF_CENTRAL_DIRECTORY.unpack_from(tail, candidate)
                disk, central_disk, disk_entries, total_entries = fields[1:5]
                central_size, central_offset, comment_length = fields[5:]
                end = candidate + END_OF_CENTRAL_DIRECTORY.size + comment_length
                absolute_candidate = file_size - search_size + candidate
                if (
                    disk == 0
                    and central_disk == 0
                    and disk_entries == total_entries == len(archive.infolist())
                    and central_offset == archive.start_dir
                    and central_size == absolute_candidate - archive.start_dir
                    and end <= len(tail)
                    and tail[candidate + END_OF_CENTRAL_DIRECTORY.size:end]
                    == archive.comment
                ):
                    return file_size - (file_size - search_size + end)
            candidate = tail.rfind(signature, 0, candidate)
    raise ValueError("valid ZIP end record was not found")


def main():
    parser = argparse.ArgumentParser(description="Reject excessive padding between APK ZIP entries")
    parser.add_argument("apk")
    parser.add_argument("--max-padding", type=int, default=MAX_PADDING_BYTES)
    args = parser.parse_args()

    try:
        gap, location = largest_internal_gap(args.apk)
        trailing_bytes = trailing_data_size(args.apk)
    except zipfile.BadZipFile:
        print("ERROR: APK ZIP data is invalid", file=sys.stderr)
        return 2
    except OSError:
        print("ERROR: could not read APK input", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"ERROR: could not inspect APK ZIP layout: {error}", file=sys.stderr)
        return 2

    if gap > args.max_padding:
        print(
            f"ERROR: APK contains {gap} bytes of internal padding {location}; "
            f"maximum is {args.max_padding} bytes. Repackage from a fresh APK output.",
            file=sys.stderr,
        )
        return 1
    if trailing_bytes:
        print(
            f"ERROR: APK contains {trailing_bytes} bytes after the ZIP end record; "
            "repackage from a canonical APK output.",
            file=sys.stderr,
        )
        return 1

    print(f"APK internal ZIP padding is bounded (largest gap: {gap} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
