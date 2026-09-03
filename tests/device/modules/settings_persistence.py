#!/usr/bin/env python3
"""Verify and restore one safe persisted product setting."""

from __future__ import annotations

from module_support import assert_foreground, module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    baseline, changed = session.assert_setting_persistence()
    assert_foreground("after settings persistence restoration")
    print(f"Safe setting persisted as {changed} and was restored to {baseline}.")


module_main(main)
