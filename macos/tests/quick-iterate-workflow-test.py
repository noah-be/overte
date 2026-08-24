#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "macos-quick-iterate.yml"


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    required = (
        "name: macOS Quick Iterate",
        "rebuild:",
        "artifact_run_id:",
        "if: github.event_name == 'workflow_dispatch'",
        "gh workflow run macos-bootstrap.yml --repo \"$GH_REPO\"",
        "gh workflow run macos-runtime.yml --repo \"$GH_REPO\"",
        "-f run_online=false -f run_serverless=true -f run_tutorial=true",
        "-f run_online=true -f run_serverless=false -f run_tutorial=false",
        "tutorial_run_id",
        "hub_run_id",
        '[[ "$tutorial_status" == "completed" && "$hub_status" == "completed" ]]',
        "Tutorial and Hub run concurrently",
        "-f run_performance=false -f profile_matrix_mode=off",
        "-f run_online_loading=false",
        "-f stability_iterations=0",
        "-f run_transition=false -f online_location=hifi://overte_hub",
        '[[ "$SOURCE_REF" != "apple-macos" ]]',
        'gh run cancel "$ARTIFACT_RUN_ID" --repo "$GH_REPO"',
        'Restore built application checkpoint',
        "sleep 60",
    )
    for fragment in required:
        assert fragment in text, f"quick-iterate contract missing: {fragment}"

    bootstrap = (ROOT / ".github" / "workflows" / "macos-bootstrap.yml").read_text(
        encoding="utf-8"
    )
    runtime = (ROOT / ".github" / "workflows" / "macos-runtime.yml").read_text(
        encoding="utf-8"
    )
    assert "name: macOS bootstrap" in bootstrap
    assert "name: macOS runtime smoke" in runtime
    print("macOS quick-iterate workflow contract passed")


if __name__ == "__main__":
    main()
