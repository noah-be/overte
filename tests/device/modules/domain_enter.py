#!/usr/bin/env python3
"""Enter a controlled domain and verify the connection and domain-owned scene."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    snapshot, samples = session.enter_controlled_domain()
    print(f"Connected to controlled domain {snapshot['domain']['hostname']} with "
          f"{snapshot['scene']['domainMarkerCount']} markers across {len(samples)} stable samples.")


module_main(main)
