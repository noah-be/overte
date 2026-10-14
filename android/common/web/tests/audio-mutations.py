#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Mutate production output/lease behavior; effects are recorded, not Chromium audio."""
from pathlib import Path
import subprocess
import tempfile

WEB = Path(__file__).resolve().parents[1]
model = WEB / 'java/org/overte/web/WebAudioLifecycle.java'
source = model.read_text()
mutations = {
    'not-muted-by-default': ('reliable = mute(true);', 'reliable = true;'),
    'hide-does-not-mute': ('if (reliable && mute(true)) return true;', 'if (reliable) return true;'),
    'background-can-unmute': ('|| !foreground ||', '|| false ||'),
    'wrong-owner': ('ticket.owner == owner', 'true'),
    'wrong-page': ('ticket.page == page', 'true'),
    'stale-ticket': ('ticket == current', 'true'),
    'fallback-not-closed': ('closed = true; output.closeDocument();', 'closed = true;'),
    'throw-does-not-close': ('reliable = false; suspend(); return false;', 'return false;'),
}
for name, (old, new) in mutations.items():
    assert source.count(old) == 1, name
    with tempfile.TemporaryDirectory(prefix='overte-audio-mutation-') as tmp:
        stage = Path(tmp)
        target = stage / 'WebAudioLifecycle.java'
        target.write_text(source.replace(old, new))
        subprocess.run(['javac', '-d', str(stage), str(target),
            str(WEB / 'java/org/overte/web/WebLifecycleDispatch.java'),
            str(WEB / 'java/org/overte/web/WebNavigationArchive.java'),
            str(WEB / 'tests/java/org/overte/web/WebAudioLifecycleTest.java')], check=True, capture_output=True)
        result = subprocess.run(['java', '-cp', str(stage), 'org.overte.web.WebAudioLifecycleTest'], capture_output=True)
        if result.returncode == 0:
            raise AssertionError('behavior mutation escaped: ' + name)
        assert b'AssertionError' in result.stderr, (name, result.stderr)
        print('DETECTED:', name)
print('PASS: eight compiled production behavior mutations detected; no DOM/acoustic claim')
