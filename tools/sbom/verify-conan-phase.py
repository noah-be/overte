#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'provenance'))
from artifact_identity import IdentityError
from conan_inventory import verify_phase


def main():
    parser = argparse.ArgumentParser(description='Offline completed Conan phase/readiness binding; no binary execution')
    for name in ('actual-graph', 'expected-graph', 'checkpoint', 'expected-source-sha',
                 'expected-graph-sha256', 'expected-manifest-sha256', 'expected-recipe-index-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--phase', choices=('bootstrap', 'host-tools', 'target'), required=True)
    args = parser.parse_args()
    try:
        result = verify_phase(args.actual_graph, args.expected_graph, args.checkpoint,
                              args.expected_source_sha, args.phase, args.expected_graph_sha256,
                              args.expected_manifest_sha256, args.expected_recipe_index_sha256)
    except IdentityError as error:
        print(str(error), file=sys.stderr); return 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('CONAN_INPUT_INVALID', file=sys.stderr); return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
