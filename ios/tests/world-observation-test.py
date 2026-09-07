#!/usr/bin/env python3
"""Host execution of the actual iOS observation adapter/startup/writer."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--proposal-root", type=Path)
parser.add_argument("--simulator-opt-in", action="store_true")
args = parser.parse_args()
spec = importlib.util.spec_from_file_location("inspect_world", ROOT / "ios/tools/inspect-world-observation.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)
with tempfile.TemporaryDirectory(prefix="ios-world-observation-") as temporary:
    scratch = Path(temporary)
    overlay = scratch / "source"
    files = ["ios/render/WorldObservation.h", "ios/render/WorldObservation.cpp",
             "ios/render/InstallWorldObservation.cpp", "ios/tests/world-observation-test.cpp",
             "libraries/shared/src/shared/IOSRuntimeLogging.h", "security/redaction/SafeDiagnostics.h"]
    for path in files:
        source = ROOT / path
        if args.proposal_root and (args.proposal_root / path).is_file():
            source = args.proposal_root / path
        target = overlay / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Gui"], text=True))
    binary = scratch / "test"
    # Keep system Qt/GCC warnings visible (GCC16 diagnoses Qt's incomplete QChar
    # SFINAE). They are not an iOS compiler result or an assertion exemption.
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-fPIC",
                    "-DOVERTE_IOS", *(["-DOVERTE_TEST_SIMULATOR_OBSERVATION"] if args.simulator_opt_in else []),
                    "-I" + str(overlay / "libraries/shared/src"),
                    str(overlay / "ios/render/WorldObservation.cpp"),
                    str(overlay / "ios/tests/world-observation-test.cpp"), *flags,
                    "-o", str(binary)], check=True, timeout=60)
    for enabled in (False, True):
        output = scratch / str(enabled)
        output.mkdir()
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", OVERTE_TEST_OUTPUT=str(output))
        command = [str(binary)] + (["--ios-world-evidence"] if enabled else [])
        subprocess.run(command, env=env, check=True, timeout=10)
        observation = output / "overte-world-observation.json"
        sample = inspector.inspect(observation)
        retained = output / "retained.json"
        subprocess.run(["python3", "-B", str(ROOT / "ios/tools/inspect-world-observation.py"),
                        str(observation), "--output", str(retained)], check=True, timeout=10)
        assert json.loads(retained.read_text()) == sample
        # Execute the actual simulator caller's collection function without any
        # simulator command; its only operation is the real offline inspector.
        documents = output / "Documents"; documents.mkdir()
        shutil.copyfile(observation, documents / observation.name)
        diagnostics = output / "diagnostics"; diagnostics.mkdir()
        smoke = (ROOT / "ios/ci/interface-world-simulator-smoke.sh").read_text()
        body = "preserve_world_observation() {" + smoke.split(
            "preserve_world_observation() {", 1)[1].split("\n}\n\nfinish()", 1)[0] + "\n}"
        subprocess.run(["bash", "-c", "set -euo pipefail\n" + body + "\npreserve_world_observation"],
                       env=dict(env, diagnostics_dir=str(diagnostics), data_container=str(output),
                                stem="fixture", script_dir=str(ROOT / "ios/ci")),
                       check=True, timeout=10)
        assert json.loads((diagnostics / "fixture-world-observation.json").read_text()) == sample
        assert observation.stat().st_mode & 0o777 == 0o600
        assert sample["producer"] == ("generation-present-v1" if args.proposal_root else "entity-counts-only")
        rejected = dict(sample, status="ACCEPTED")
        observation.write_text(json.dumps(rejected))
        try:
            inspector.inspect(observation)
        except ValueError:
            pass
        else:
            raise AssertionError("acceptance relabel was admitted")
        observation.write_text('{"schemaVersion":1,"schemaVersion":1}')
        try:
            inspector.inspect(observation)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate was admitted")
print("PASS actual Qt observation/startup/writer; container path substituted; native/render acceptance unproved")
