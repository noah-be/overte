#!/usr/bin/env python3
"""Offline exact artifact identity consumer. Does not sign or run a build."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'provenance'))
from artifact_identity import EVIDENCE_KEYS, IdentityError, read_record, validate
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',required=True,type=Path)
    parser.add_argument('--artifact',required=True,type=Path)
    parser.add_argument('--expected-source-sha',required=True)
    parser.add_argument('--expected-inputs',required=True,type=Path)
    parser.add_argument('--minimum-version',type=int,default=0)
    for key in EVIDENCE_KEYS:
        parser.add_argument('--'+key,required=True,type=Path)
    args=parser.parse_args()
    try:
        result=validate(read_record(args.record),args.artifact,{key:getattr(args,key) for key in EVIDENCE_KEYS},
                        args.expected_source_sha,read_record(args.expected_inputs),args.minimum_version)
    except (IdentityError,OSError,TypeError,KeyError,ValueError):
        print('ARTIFACT_IDENTITY_REJECTED',file=sys.stderr)
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0
if __name__ == '__main__': raise SystemExit(main())
