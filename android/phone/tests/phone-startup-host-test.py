#!/usr/bin/env python3
"""Run device-free Phone startup harnesses (C++, Qt6Core, Java and Node required).

The pinned Etc2Comp regression additionally requires --etc-source. This suite
neither builds an APK nor installs or connects to a device.
"""
import argparse
from pathlib import Path
import subprocess
import sys

TESTS = (
    'test_animation_curve_optin.py',
    'test_animation_curve_parser.py',
    'test_animation_curve_skip.py',
    'test_cache_lifecycle.py',
    'test_collision_priority.py',
    'test_ktx_header_probe.py',
    'test_lazy_shader_sources.py',
    'test_lifecycle_binding.py',
    'test_loading_frame_cap.py',
    'test_loading_worker_override.py',
    'test_navigation_supersession.py',
    'test_phone_cache_namespace.py',
    'test_phone_ktx_probe_pool.py',
    'test_present_intervals.py',
    'test_qml_fatal_diagnostics.py',
    'test_resource_priority_map.py',
    'test_retained_profile_binding.py',
    'test_serverless_navigation_ticket.py',
    'test_texture_streaming_priority.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etc-source', type=Path,
                        help='Pinned Etc2Comp source tree containing EtcLib')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent / 'instrumentation'
    commands = [(name, []) for name in TESTS]
    if args.etc_source:
        source = args.etc_source.resolve(strict=True)
        if not (source / 'EtcLib').is_dir():
            parser.error('--etc-source must contain EtcLib')
        commands.append(('test_rectangular_etc_mips.py', [str(source)]))
    failures = []
    for name, arguments in commands:
        print('RUN ' + name, flush=True)
        try:
            result = subprocess.run([sys.executable, str(directory / name), *arguments],
                                    check=False, timeout=120)
            if result.returncode:
                failures.append(name)
        except subprocess.TimeoutExpired:
            failures.append(name + ' (timeout)')
    if not args.etc_source:
        print('NOT RUN: rectangular ETC mip regression requires --etc-source')
    print(f'Phone startup host harnesses: {len(commands)} run, {len(failures)} failed')
    for name in failures:
        print('FAIL ' + name)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
