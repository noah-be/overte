#!/usr/bin/env python3
"""Retire obsolete bundles only after all live branches and replacement archives pass.

The default is a read-only plan. --apply rechecks the plan, verifies replacements,
then removes only older dependency releases/tags in the authorized fork. Exact
temporary ruleset exclusions are restored even when a deletion fails.
"""

import argparse
import copy
import json
from pathlib import Path
import re
import subprocess

from check import ROOT, POLICY, REPOSITORY, FAMILIES, PolicyError, api, audit, pages, remote_heads, run
from verify import verify


def mutation(endpoint, method, directory, body=None):
    if not endpoint.startswith(f"repos/{REPOSITORY}/"):
        raise PolicyError("Mutation outside authorized fork")
    if api(f"repos/{REPOSITORY}")["full_name"] != REPOSITORY:
        raise PolicyError("Repository ownership mismatch")
    command = ["gh", "api", "--method", method, endpoint]
    if body is not None:
        payload = directory / "request.json"
        payload.write_text(json.dumps(body))
        command += ["--input", str(payload)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def retirement_candidates(plan):
    candidates = plan["retirement_candidates"]
    for tag in candidates:
        family = next((f for f, prefix in FAMILIES.items()
                       if re.fullmatch(prefix + r"[1-9][0-9]*", tag)), None)
        if family is None:
            raise PolicyError("Unknown retirement candidate")
        current = plan["policy"]["bundles"][family]["tag"]
        prefix = FAMILIES[family]
        if int(tag[len(prefix):]) >= int(current[len(prefix):]):
            raise PolicyError(f"Refusing to retire a current or newer candidate: {tag}")
    return candidates


def retire(root, directory, conan):
    plan = audit(root, allow_retiring=True)
    candidates = retirement_candidates(plan)
    if not candidates:
        print("No obsolete dependency releases or tags")
        return
    if json.loads((root / POLICY).read_text()) != plan["policy"]:
        raise PolicyError("Local policy differs from live main")
    verify(root, directory, conan)
    # Downloads may take minutes; do not rely on an old branch snapshot.
    plan = audit(root, allow_retiring=True)
    if retirement_candidates(plan) != candidates:
        raise PolicyError("Retirement candidates changed; retry")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "retirement-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    releases = pages(f"repos/{REPOSITORY}/releases")
    old = [r for r in releases if r["tag_name"] in candidates]
    (directory / "retired-releases.json").write_text(json.dumps(old, indent=2) + "\n")
    rules = [api(f"repos/{REPOSITORY}/rulesets/{r['id']}")
             for r in pages(f"repos/{REPOSITORY}/rulesets") if r["target"] == "tag"]
    changed = []
    keys = ("name", "target", "enforcement", "conditions", "rules", "bypass_actors")
    try:
        for rule in rules:
            if rule["source"] != REPOSITORY or rule["source_type"] != "Repository":
                raise PolicyError("Cannot alter inherited or foreign tag rules")
            if rule["enforcement"] != "active":
                continue
            original = {k: copy.deepcopy(rule[k]) for k in keys}
            payload = copy.deepcopy(original)
            excludes = payload["conditions"]["ref_name"]["exclude"]
            excludes.extend(f"refs/tags/{t}" for t in candidates if f"refs/tags/{t}" not in excludes)
            endpoint = f"repos/{REPOSITORY}/rulesets/{rule['id']}"
            (directory / f"ruleset-{rule['id']}-before.json").write_text(json.dumps(original, indent=2))
            if api(endpoint)["source"] != REPOSITORY:
                raise PolicyError("Ruleset ownership changed")
            changed.append((endpoint, original))
            mutation(endpoint, "PUT", directory, payload)
            saved = api(endpoint)
            if any(saved[k] != v for k, v in payload.items()):
                raise PolicyError("Ruleset update readback mismatch")
        if remote_heads() != plan["heads"]:
            raise PolicyError("Branches moved before retirement; retry")
        for release in old:
            endpoint = f"repos/{REPOSITORY}/releases/{release['id']}"
            live = api(endpoint)
            if live["tag_name"] != release["tag_name"] or live["url"] != f"https://api.github.com/{endpoint}":
                raise PolicyError("Release ownership or identity changed")
            mutation(endpoint, "DELETE", directory)
        url = f"https://github.com/{REPOSITORY}.git"
        bare = directory / "retirement.git"
        if not bare.exists():
            run("git", "init", "--bare", str(bare))
        # --get-url does not account for pushInsteadOf; inspect the push URL.
        run("git", "-C", str(bare), "config", "remote.authorized.url", url)
        if run("git", "-C", str(bare), "remote", "get-url", "--push", "--all", "authorized").strip() != url:
            raise PolicyError("Git push URL was rewritten")
        existing = {tag: sha for tag, sha in candidates.items() if sha is not None}
        if existing:
            if api(f"repos/{REPOSITORY}")["full_name"] != REPOSITORY:
                raise PolicyError("Repository ownership changed")
            run("git", "-C", str(bare), "push", "--atomic",
                *[f"--force-with-lease=refs/tags/{tag}:{sha}" for tag, sha in existing.items()],
                url, *[f":refs/tags/{tag}" for tag in existing])
    finally:
        # Restore every changed rule, even if restoring another one fails.
        failures = []
        for endpoint, original in changed:
            try:
                if api(endpoint)["source"] != REPOSITORY:
                    raise PolicyError("Ruleset ownership changed")
                mutation(endpoint, "PUT", directory, original)
                restored = api(endpoint)
                if any(restored[k] != v for k, v in original.items()):
                    raise PolicyError("Ruleset restoration readback mismatch")
            except Exception as error:
                failures.append(str(error))
        if failures:
            raise PolicyError("Ruleset restoration failed: " + "; ".join(failures))
    result = audit(root)
    (directory / "retirement-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Obsolete dependency releases retired; current bundles and tag protection verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--conan", default="conan")
    args = parser.parse_args()
    if args.apply:
        if not args.directory:
            parser.error("--apply requires an evidence/download directory")
        retire(args.root, args.directory.resolve(), args.conan)
    else:
        plan = audit(args.root, allow_retiring=True)
        retirement_candidates(plan)
        print(json.dumps(plan, indent=2))
