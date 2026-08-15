#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Keep worker-thread domain updates behind the QAction event-loop boundary."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MENU = (ROOT / "interface/src/Menu.cpp").read_text(encoding="utf-8")

connection = re.search(
    r"connect\(domainAccountManager\.data\(\),\s*"
    r"&DomainAccountManager::hasLogInChanged,\s*"
    r"domainLogin,\s*\[domainLogin\]\(bool hasLogIn\)\s*\{"
    r"\s*domainLogin->setVisible\(hasLogIn\);\s*\}\);",
    MENU,
    re.DOTALL,
)
assert connection is not None, (
    "DomainAccountManager emits from the NodeList thread; the domain-login QAction "
    "must be the connect context so Qt queues delivery to the QAction thread and "
    "disconnects it automatically on destruction"
)

unsafe_connection = re.search(
    r"connect\(domainAccountManager\.data\(\),\s*"
    r"&DomainAccountManager::hasLogInChanged,\s*"
    r"\[domainLogin\]",
    MENU,
    re.DOTALL,
)
assert unsafe_connection is None, "context-free QAction capture reintroduces the NodeList-thread SIGSEGV"

print("iOS domain-login QAction thread contract passed")
