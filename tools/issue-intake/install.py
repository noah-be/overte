#!/usr/bin/env python3
"""Install the reviewed local intake code and discoverable Codex skill."""
import argparse
import datetime
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
BEGIN = "<!-- overte-issue-intake:start -->"
END = "<!-- overte-issue-intake:end -->"


def install(home, codex_home):
    tool = home / ".local/share/overte-issue-intake"
    skill = codex_home / "skills/overte-issue-intake"
    binary = home / ".local/bin/overte-issue"
    instructions = codex_home / "AGENTS.md"
    if (codex_home / "AGENTS.override.md").exists():
        raise RuntimeError("A global AGENTS.override.md exists; review its instruction precedence before installation")
    for directory in (tool / "tools/issue-intake", tool / ".github", skill / "agents", binary.parent):
        directory.mkdir(parents=True, exist_ok=True)
    for module in ("intake.py", "acceptance.py", "guard.py"):
        shutil.copy2(ROOT / "tools/issue-intake" / module, tool / "tools/issue-intake" / module)
    shutil.copy2(ROOT / ".github/issue-policy.json", tool / ".github/issue-policy.json")
    for relative in ("SKILL.md", "agents/openai.yaml"):
        shutil.copy2(ROOT / "tools/issue-intake/skill" / relative, skill / relative)
    # An executable Python launcher avoids shell expansion of user-supplied text.
    binary.write_text("#!/usr/bin/env python3\nimport os, sys\nos.execv(sys.executable, [sys.executable, "
                      + repr(str(tool / "tools/issue-intake/intake.py")) + "] + sys.argv[1:])\n")
    binary.chmod(0o755)
    block = f"""{BEGIN}
## Overte issue intake

- Whenever work involves creating, structuring, labeling, updating, or closing an
  issue in `noah-be/overte`, read `{skill / 'SKILL.md'}` and use the
  `overte-issue` validated workflow. This applies even when the session starts
  outside an Overte checkout or while working on a different task.
- Load the current repository policy through `overte-issue policy` before issue
  writes. Use the helper for managed fields; do not substitute raw `gh issue
  create/edit`, API calls, or connectors when validation rejects an input.
- The user's ordinary issue request authorizes that requested operation; do not
  ask for an extra confirmation merely to use the helper. Preserve unknown facts
  honestly, existing evidence, and the user's current active scope.
- This supplements the existing English-language, label, and fork-only write
  rules. The authoritative policy is versioned in `noah-be/overte` on `main`.
{END}"""
    previous = instructions.read_text() if instructions.exists() else ""
    if BEGIN in previous or END in previous:
        if previous.count(BEGIN) != 1 or previous.count(END) != 1 or previous.index(BEGIN) > previous.index(END):
            raise RuntimeError("Malformed routing block; preserve and review the existing instructions")
        start, remainder = previous.split(BEGIN, 1)
        _, finish = remainder.split(END, 1)
        updated = start + block + finish
    else:
        updated = previous.rstrip() + "\n\n" + block + "\n"
    if updated != previous:
        if instructions.exists():
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            shutil.copy2(instructions, instructions.with_name("AGENTS.md.before-issue-intake-" + stamp))
        temporary = instructions.with_name("AGENTS.md.issue-intake.tmp")
        temporary.write_text(updated)
        temporary.replace(instructions)
    print(f"Installed tool: {binary}\nInstalled skill: {skill}\nGlobal routing: {instructions}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home(), help="Installation home; also supports isolated fixture tests")
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    codex_home = args.codex_home or Path(os.environ.get("CODEX_HOME", str(args.home / ".codex")))
    install(args.home, codex_home)
