#!/usr/bin/env python3
"""Deterministic Pico runtime simulations for failure and lifecycle sequences."""

from dataclasses import dataclass, field
import unittest


@dataclass
class RuntimeModel:
    focused: bool = False
    session_running: bool = False
    controllers: dict[str, bool] = field(default_factory=lambda: {"left": False, "right": False})
    buttons: set[str] = field(default_factory=set)
    audio_route: str = "dummy"
    connected: bool = False
    retry: int = 0

    def event(self, name: str, **data) -> None:
        if name == "resume":
            self.session_running = True
        elif name in {"pause", "session_lost"}:
            self.session_running = self.focused = False
            self.buttons.clear()
            self.controllers = {"left": False, "right": False}
        elif name == "focus":
            self.focused = self.session_running and data["active"]
            if not self.focused:
                self.buttons.clear()
        elif name == "tracking":
            self.controllers[data["hand"]] = self.session_running and data["valid"]
            if not data["valid"]:
                self.buttons = {button for button in self.buttons if not button.startswith(data["hand"] + ":")}
        elif name == "button":
            key = f"{data['hand']}:{data['button']}"
            if self.focused and self.controllers[data["hand"]] and data["pressed"]:
                self.buttons.add(key)
            else:
                self.buttons.discard(key)
        elif name == "network":
            self.connected = data["connected"]
            self.retry = 0 if self.connected else min(self.retry + 1, 5)
        elif name == "audio":
            self.audio_route = data["route"] if data["available"] else "dummy"


class PicoRuntimeSimulationTests(unittest.TestCase):
    def active(self) -> RuntimeModel:
        model = RuntimeModel()
        model.event("resume")
        model.event("focus", active=True)
        model.event("tracking", hand="left", valid=True)
        return model

    def test_button_trigger_and_grip_require_focus_and_tracking(self):
        model = self.active()
        for button in ("trigger", "grip", "menu"):
            model.event("button", hand="left", button=button, pressed=True)
        self.assertEqual(model.buttons, {"left:trigger", "left:grip", "left:menu"})

    def test_tracking_loss_neutralizes_only_the_lost_controller(self):
        model = self.active()
        model.event("tracking", hand="right", valid=True)
        model.event("button", hand="left", button="trigger", pressed=True)
        model.event("button", hand="right", button="grip", pressed=True)
        model.event("tracking", hand="left", valid=False)
        self.assertEqual(model.buttons, {"right:grip"})
        model.event("tracking", hand="left", valid=True)
        self.assertTrue(model.controllers["left"])

    def test_focus_loss_and_pause_cannot_leave_stuck_input(self):
        model = self.active()
        model.event("button", hand="left", button="trigger", pressed=True)
        model.event("focus", active=False)
        self.assertFalse(model.buttons)
        model.event("pause")
        self.assertFalse(any(model.controllers.values()))

    def test_session_loss_then_resume_starts_neutral(self):
        model = self.active()
        model.event("button", hand="left", button="grip", pressed=True)
        model.event("session_lost")
        model.event("resume")
        self.assertTrue(model.session_running)
        self.assertFalse(model.focused)
        self.assertFalse(model.buttons)

    def test_network_retries_are_bounded_and_reset_on_reconnect(self):
        model = RuntimeModel()
        for _ in range(20):
            model.event("network", connected=False)
        self.assertEqual(model.retry, 5)
        model.event("network", connected=True)
        self.assertTrue(model.connected)
        self.assertEqual(model.retry, 0)

    def test_audio_route_falls_back_and_recovers_without_hardware(self):
        model = RuntimeModel()
        model.event("audio", route="pico-microphone", available=True)
        self.assertEqual(model.audio_route, "pico-microphone")
        model.event("audio", route="pico-microphone", available=False)
        self.assertEqual(model.audio_route, "dummy")
        model.event("audio", route="usb-headset", available=True)
        self.assertEqual(model.audio_route, "usb-headset")


if __name__ == "__main__":
    unittest.main(verbosity=2)
