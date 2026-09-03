#!/usr/bin/env python3
"""Point a Jenkins Pipeline job at the shared, repository-owned E2E control plane."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET


BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
SCRIPT_PATH = "tests/device/jenkins/Jenkinsfile"


def scm_definition(repository: str, branch: str) -> ET.Element:
    definition = ET.Element(
        "definition", {"class": "org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition",
                       "plugin": "workflow-cps"})
    scm = ET.SubElement(definition, "scm", {
        "class": "hudson.plugins.git.GitSCM", "plugin": "git"})
    ET.SubElement(scm, "configVersion").text = "2"
    remotes = ET.SubElement(scm, "userRemoteConfigs")
    remote = ET.SubElement(remotes, "hudson.plugins.git.UserRemoteConfig")
    ET.SubElement(remote, "url").text = repository
    branches = ET.SubElement(scm, "branches")
    spec = ET.SubElement(branches, "hudson.plugins.git.BranchSpec")
    ET.SubElement(spec, "name").text = f"*/{branch}"
    ET.SubElement(scm, "doGenerateSubmoduleConfigurations").text = "false"
    ET.SubElement(scm, "submoduleCfg", {"class": "empty-list"})
    ET.SubElement(scm, "extensions")
    ET.SubElement(definition, "scriptPath").text = SCRIPT_PATH
    ET.SubElement(definition, "lightweight").text = "true"
    return definition


def migrate(source: Path, destination: Path, repository: str, branch: str,
            *, disable: bool = False) -> None:
    if not BRANCH.fullmatch(branch) or ".." in branch.split("/"):
        raise ValueError("branch is invalid")
    repository_path = Path(repository).expanduser()
    if (not repository_path.is_absolute() or not repository_path.is_dir()
            or not (repository_path / ".git").exists()):
        raise ValueError("repository must be an absolute local Git worktree")
    tree = ET.parse(source)
    root = tree.getroot()
    if root.tag != "flow-definition":
        raise ValueError("only Pipeline job configurations can be migrated")
    old = root.find("definition")
    if old is None:
        raise ValueError("Pipeline job has no definition")
    position = list(root).index(old)
    root.remove(old)
    root.insert(position, scm_definition(str(repository_path.resolve()), branch))
    if disable:
        disabled = root.find("disabled")
        if disabled is None:
            disabled = ET.SubElement(root, "disabled")
        disabled.text = "true"
    ET.indent(tree, space="  ")
    tree.write(destination, encoding="utf-8", xml_declaration=True)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--disable", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        migrate(args.input, args.output, args.repository, args.branch,
                disable=args.disable)
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"error: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
