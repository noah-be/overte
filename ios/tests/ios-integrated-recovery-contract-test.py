#!/usr/bin/env python3
"""Protect durable checkpoints and observability of the iOS integrated build."""

from pathlib import Path
import re
import os
import subprocess
import textwrap
import tempfile

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ios-integrated.yml"

def require(pattern: str, text: str, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)

def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    preflight = workflow.split("      - name: Toolchain preflight\n", 1)[1].split("\n      - name:", 1)[0]
    for component in ("HOST", "IOS"):
        producer = "host" if component == "HOST" else "ios"
        assert f"QT_{component}_TRUSTED_ARTIFACT_RESTORED: ${{{{ steps.qt-{producer}-apple-ios-artifact.outputs.restored }}}}" in preflight
    # Execute the real shell admission checks, before native validation, with
    # cache, same-branch artifact and validated trusted-branch restore outcomes.
    admission = textwrap.dedent(preflight.split("        run: |\n", 1)[1]).split("ios/tools/prepare-qt-ios.sh validate", 1)[0]
    groups = [
        ["QT_HOST_CACHE_HIT", "QT_HOST_ARTIFACT_RESTORED", "QT_HOST_TRUSTED_ARTIFACT_RESTORED"],
        ["QT_IOS_CACHE_HIT", "QT_IOS_ARTIFACT_RESTORED", "QT_IOS_TRUSTED_ARTIFACT_RESTORED"],
        ["V8_CACHE_HIT", "V8_ARTIFACT_RESTORED"],
    ]
    import itertools
    for choices in itertools.product(*[range(-1, len(group)) for group in groups]):
        env = dict(os.environ, **{key: "false" for group in groups for key in group})
        for group, choice in zip(groups, choices):
            if choice >= 0:
                env[group[choice]] = "true"
        result = subprocess.run(["bash", "-e", "-c", admission], env=env, timeout=5)
        assert (result.returncode == 0) == all(choice >= 0 for choice in choices), choices
    assert "PRESERVE_REUSABLE_DATA: ${{ inputs.preserve_reusable_data }}" in workflow
    integrity_step = workflow.split("      - name: Validate and compact audited device dependencies\n", 1)[1].split("\n      - name:", 1)[0]
    integrity_shell = textwrap.dedent(integrity_step.split("        run: |\n", 1)[1])
    # Run the actual workflow script with an instrumented Conan command. This
    # proves preservation removes the duplicate check without dropping the
    # post-clean validation or swallowing a failed check/cleanup.
    with tempfile.TemporaryDirectory(prefix="ios-conan-integrity-test-") as temporary:
        directory = Path(temporary)
        activate = directory / "build-ios/tooling-venv/bin/activate"
        activate.parent.mkdir(parents=True)
        activate.write_text('''conan() {
  printf '%s\\n' "$*" >> "$CONAN_TEST_LOG"
  calls=$(wc -l < "$CONAN_TEST_LOG")
  if [ "$calls" -eq "$CONAN_TEST_FAIL_AT" ]; then return 19; fi
  return 0
}
''')
        check, clean = 'cache check-integrity *', 'cache clean * --build --temp'
        cases = [('true', 0, [check]), ('false', 0, [check, clean, check]),
                 ('', 0, [check]), ('true', 1, [check]),
                 ('false', 1, [check]), ('false', 2, [check, clean]),
                 ('false', 3, [check, clean, check])]
        for index, (preserve, fail_at, expected) in enumerate(cases):
            log = directory / f'calls-{index}.log'
            env = dict(os.environ, PRESERVE_REUSABLE_DATA=preserve,
                       CONAN_TEST_LOG=str(log), CONAN_TEST_FAIL_AT=str(fail_at))
            result = subprocess.run(['bash', '-e', '-c', integrity_shell],
                                    cwd=directory, env=env, capture_output=True,
                                    text=True, timeout=5)
            assert log.read_text().splitlines() == expected, (preserve, fail_at)
            assert result.returncode == (19 if fail_at else 0), result.stderr
    integrated = workflow[workflow.index("  integrated-configure:"):]
    names = [
        "Restore validated Conan package cache",
        "Probe durable Conan package checkpoint",
        "Restore durable Conan package checkpoint",
        "Restore partial Conan package checkpoint",
        "Resolve audited device dependencies",
        "Save partial Conan package checkpoint after dependency failure",
        "Validate and compact audited device dependencies",
        "Create durable Conan package checkpoint",
        "Upload durable Conan package checkpoint",
        "Save validated Conan package cache",
    ]
    positions = [integrated.index(name) for name in names]
    if positions != sorted(positions):
        raise AssertionError("Conan recovery stages are not fail-safe ordered")
    conan = integrated[positions[0]:positions[-1]]
    require(r"--kind conan", conan, "Conan must use the durable artifact format")
    require(r"resolve-device-dependencies\.outcome == 'failure'", conan,
            "dependency failure must save partial Conan progress")
    require(r"conan cache check-integrity \"\*\"[\s\S]*conan cache clean[\s\S]*conan cache check-integrity \"\*\"",
            conan, "only validated compact Conan state may become durable")
    require(r"retention-days: 30", conan, "durable Conan recovery must outlive cache eviction")

    for phase, raw_log in (
        ("conan-dependencies", "conan-dependencies.log"),
        ("conan-checkpoint", "conan-checkpoint.log"),
        ("client-configure", "configure.log"),
        ("client-build", "xcode-build.log"),
        ("client-package", "package.log"),
    ):
        require(rf"--phase {phase}[\s\S]*?--output-log [^\n]*{re.escape(raw_log)}",
                integrated, f"{phase} must retain complete output")
    for metric in ("--sample-interval 5", "--publish-interval 30", "--inactivity-timeout", "--max-runtime"):
        if integrated.count(metric) < 5:
            raise AssertionError(f"all long phases must expose telemetry: {metric}")
    require(r"Upload runner telemetry and bounded stall diagnostics[\s\S]*if: always\(\)", integrated,
            "resource and stall evidence must survive every job result")
    require(r"Sanitize failure diagnostics[\s\S]*ci-raw-diagnostics/\*\.log", integrated,
            "raw logs must be sanitized before upload")
    if re.search(r"actions/cache/(?:restore|save)@[0-9a-f]{40}[\s\S]{0,300}build-ios/device", integrated):
        raise AssertionError("absolute-path Xcode state must not be cached across runners")
    if "build-ios/device/CMakeCache.txt" in workflow:
        raise AssertionError("CMakeCache.txt must never enter recovery storage")
    print("iOS integrated recovery contract passed")

if __name__ == "__main__":
    main()
