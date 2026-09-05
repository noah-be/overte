#!/usr/bin/env python3
"""Source-only regression guard; actual UIKit/VoiceOver acceptance is pending."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / "ios/ui/IOSTouchUiMetrics.mm").read_text()
ordinary = source[source.index("#else\n    OverteIOSAccessibilityElement* element"):
                  source.index("void dismissIOSKeyboard()")]
assert "existingElements.count == 1" in ordinary
assert "element = existingElements.firstObject" in ordinary
assert "element.accessibilityIdentifier isEqualToString:identifier" in ordinary
assert "[overlay convertRect:controlFrame fromView:window]" in ordinary
assert ordinary.count("if (targetChanged)") == 2
assignment = ordinary.index("overlay.accessibilityElements = @[element]")
notification = ordinary.index("UIAccessibilityPostNotification(")
assert ordinary.rfind("if (targetChanged)", 0, assignment) == ordinary.rfind(
    "if (targetChanged)", 0, notification)
assert "element.activationHandler = activationHandler" in ordinary
assert "OverteIOSE2EAccessibilityButton" not in ordinary
print("PASS ordinary accessibility identity/focus/coordinate source guards; UIKit/VoiceOver unexecuted")
