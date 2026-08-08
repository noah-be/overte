#!/usr/bin/env python3
"""Source contracts for Pico local-avatar hot paths."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MY_AVATAR = (ROOT / "interface/src/avatar/MyAvatar.cpp").read_text(encoding="utf-8")
AVATAR_MANAGER = (ROOT / "interface/src/avatar/AvatarManager.cpp").read_text(encoding="utf-8")
PHYSICS_ENGINE = (ROOT / "libraries/physics/src/PhysicsEngine.cpp").read_text(encoding="utf-8")


class PicoAvatarHotpathTests(unittest.TestCase):
    def test_periodic_avatar_profilers_are_not_always_on(self):
        for marker in (
            "PICO_AVATAR_STAGES",
            "PICO_MY_AVATAR_UPDATE",
            "PICO_MY_AVATAR_SIM",
            "picoUpdateLogCounter",
            "picoSimLogCounter",
        ):
            self.assertNotIn(marker, MY_AVATAR + AVATAR_MANAGER)

    def test_local_body_optimization_remains_scoped_to_android(self):
        marker = '_myAvatar->setProperty("shouldRenderLocally", false);'
        marker_at = AVATAR_MANAGER.index(marker)
        android_guard_at = AVATAR_MANAGER.rfind("#if defined(Q_OS_ANDROID)", 0, marker_at)
        guard_end_at = AVATAR_MANAGER.index("#endif", marker_at)
        self.assertGreater(android_guard_at, AVATAR_MANAGER.rfind("void AvatarManager::init()", 0, marker_at))
        self.assertGreater(guard_end_at, marker_at)

    def test_avatar_update_and_network_send_remain_present(self):
        self.assertIn("_myAvatar->update(deltaTime);", AVATAR_MANAGER)
        self.assertIn("_myAvatar->sendAvatarDataPacket();", AVATAR_MANAGER)
        self.assertIn("simulate(deltaTime, true);", MY_AVATAR)

    def test_physics_profiler_is_not_always_on_but_hitch_cap_remains(self):
        self.assertNotIn("PICO_PHYSICS_STEP", PHYSICS_ENGINE)
        self.assertNotIn("accumulatedSubsteps", PHYSICS_ENGINE)
        self.assertIn("dt > 0.050f ? 1", PHYSICS_ENGINE)
        self.assertIn("dt > 0.033f ? 2", PHYSICS_ENGINE)
        self.assertIn("stepSimulationWithSubstepCallback", PHYSICS_ENGINE)


if __name__ == "__main__":
    unittest.main()
