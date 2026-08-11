#!/usr/bin/env python3
"""Source contracts for Pico local-avatar hot paths."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
MY_AVATAR = (ROOT / "interface/src/avatar/MyAvatar.cpp").read_text(encoding="utf-8")
AVATAR_MANAGER = (ROOT / "interface/src/avatar/AvatarManager.cpp").read_text(encoding="utf-8")
PHYSICS_ENGINE = (ROOT / "libraries/physics/src/PhysicsEngine.cpp").read_text(encoding="utf-8")
ENTITY_SIMULATION = (ROOT / "libraries/entities/src/EntitySimulation.cpp").read_text(encoding="utf-8")
ENTITY_RENDERER = (ROOT / "libraries/entities-renderer/src/EntityTreeRenderer.cpp").read_text(encoding="utf-8")
PICK = (ROOT / "libraries/pointers/src/Pick.cpp").read_text(encoding="utf-8")
PICK_MANAGER = (ROOT / "libraries/pointers/src/PickManager.cpp").read_text(encoding="utf-8")
POINTER = (ROOT / "libraries/pointers/src/Pointer.cpp").read_text(encoding="utf-8")
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")


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

    def test_entity_profilers_are_not_always_on(self):
        combined = ENTITY_SIMULATION + ENTITY_RENDERER
        for marker in (
            "PICO_ENTITY_SIM_STAGES",
            "PICO_ENTITY_UPDATE_STAGES",
            "PICO_SLOW_RENDERABLE",
            "PicoSimulationStats",
            "PicoEntityUpdateStats",
        ):
            self.assertNotIn(marker, combined)

    def test_entity_update_paths_remain_present(self):
        for call in (
            "expireMortalEntities(now);",
            "callUpdateOnEntitiesThatNeedIt(now);",
            "moveSimpleKinematics(now);",
            "sortEntitiesThatMoved();",
            "processDeadEntities();",
        ):
            self.assertIn(call, ENTITY_SIMULATION)
        self.assertIn("tree->update(simulate);", ENTITY_RENDERER)
        self.assertIn("addPendingEntities(scene, transaction);", ENTITY_RENDERER)
        self.assertIn("updateChangedEntities(scene, transaction);", ENTITY_RENDERER)
        self.assertIn("checkEnterLeaveEntities();", ENTITY_RENDERER)

    def test_pointer_profilers_are_not_always_on(self):
        combined = PICK + PICK_MANAGER + POINTER
        self.assertNotIn("PICO_LATENCY_POINTER_UPDATE", combined)
        self.assertNotIn("PICO_LATENCY_PICK", combined)
        self.assertNotIn("picoUpdatedUsec", combined)
        self.assertNotIn("lastPickLog", combined)

    def test_pointer_transition_and_pick_budget_paths_remain(self):
        self.assertIn("PICO_POINTER_TRIGGER", POINTER)
        self.assertIn("generatePointerEvents(pointerID, visualPickResult);", POINTER)
        self.assertIn("usecTimestampNow() + _perFrameTimeBudget", PICK_MANAGER)
        self.assertIn("if (updateRaysThisFrame)", PICK_MANAGER)
        self.assertIn("_prevResult = pickResult;", PICK)

    def test_application_stage_profiler_is_not_always_on(self):
        self.assertNotIn("PICO_UPDATE_STAGES", APPLICATION)
        self.assertNotIn("PicoUpdateStats", APPLICATION)
        self.assertNotIn("picoAfterInputPlugins", APPLICATION)
        self.assertNotIn("picoBeforeEntityUpdate", APPLICATION)

    def test_application_pico_state_clock_and_update_paths_remain(self):
        self.assertIn("const quint64 picoUpdateStart = usecTimestampNow();", APPLICATION)
        self.assertIn("DependencyManager::get<PickManager>()->update();", APPLICATION)
        self.assertIn("DependencyManager::get<PointerManager>()->update();", APPLICATION)
        self.assertIn("getEntities()->update(true);", APPLICATION)
        self.assertIn("avatarManager->updateMyAvatar(deltaTime);", APPLICATION)
        self.assertIn("updateRenderArgs(deltaTime);", APPLICATION)


if __name__ == "__main__":
    unittest.main()
