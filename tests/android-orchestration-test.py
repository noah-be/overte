#!/usr/bin/env python3
"""Offline exact-event Android required-owner contracts; no product builds."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("android_gate_test_subject", "tools/repository-checks/android_gate.py")
ownership = load("android_owner_fixture", "tests/android-ci-test.py")
checks = load("android_outer_test_subject", "tools/repository-checks/check.py")


# Exact pre-hermetic archive-reading test bytes. Shallow CI checkouts need not
# contain this historical Git object; verify its original identity before use.
LEGACY_METADATA_BLOB = "de670465b44ca7be8d550274acbe92bdfc9e7acc"
LEGACY_METADATA_ZLIB = (
    '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'
)


def legacy_metadata_fixture():
    source = zlib.decompress(base64.b64decode(LEGACY_METADATA_ZLIB, validate=True))
    if gate._blob(source)["sha"] != LEGACY_METADATA_BLOB:
        raise ValueError("legacy metadata fixture identity changed")
    return source


# Exact old14 source bytes remain available after the future sync recipe is
# installed; shallow CI must not fetch a historical Git object for this fixture.
LEGACY_SYNC_BLOB = "55d08b65a987224ce576459cede693cfd49375f6"
LEGACY_SYNC_ZLIB = (
    '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'
)


def legacy_sync_fixture():
    raw=zlib.decompress(base64.b64decode(LEGACY_SYNC_ZLIB,validate=True))
    if gate._blob(raw)['sha']!=LEGACY_SYNC_BLOB:
        raise AssertionError('legacy sync fixture differs from its actual reviewed Git blob')
    return raw


# Exact historical21 caller/helper data; no Git-history or test-module reader.
_PROTECTED21_WORKFLOW_BYTES = (
    ('d9fefd275d9e3c6977cf9350a1945a6bbe5051b4', (
        'c-q}s>u=jO5dWUPg6WDn0Ve0Yb{;Y;ON=J#>I8|?p(qMLmd-XCSyD;LiP!dj-|?k~CClz3S<!xq$-Cq6cW<gck&~EByhsqiQZ67M'
        'iRa&VBOoJ)fO&$((Qm}_1)ZwD34`}3Wx(-|DTP~P5FQ(WAW0ljf7V`$ya{y3B_uJYB4#t<kHNp;YjM<BBP2<~(3LWP3;CN6F-w5!'
        'KOGV$cxqsNFev@xv&bK_IHLc8S%H9xY&-M@5N5y9DF1yMvzuWU-?{<ii6{KAK8;36D$L1*urxxwMtCz$wW|7G0NiIZk$1;ir4bQh'
        'AbvbaLJ)wvQ|f~=WB?@RCV~RXB*+VP$RLhG@S=j;p_hiDBXNgp)u0=6$j}QptR=uERLN9|`f(&6LZy+=3)b+bpE3rKKa;y77N?2a'
        'vd}vkdgt+n4`f8eI32WMiu~=O71~ic82}?6KUx|FL-OfUl}ma7UheRav^4T9^5h9wFVXm8FB$=F4?GTXccXS!P!U4m#5vwLm~BdC'
        's}Gun29mt>KJ`L6q`vaS7HTO$@gg5Whel4qVr2pY>brQLP@9180#A4jk5lG@wyk#4qZG{<2`LcB#U&ANCzM-h4;gk!8oH86-M<K6'
        'tDvg9wkz?IL=%rj#m)Z#MRkpoV}OzNR$J3;*?8bv33D=VlyBXM_G}WaAshOVuuuU6C}0l83?VPP^=5oSS!_emw&zIEqd5Ayx-(CG'
        'A5GMfdM_uwp-F-W>3hrtgZwua5PDG~Twap~bBw`?JK7DdFjM#<i@rh#+3aOf1b1W_NC#;oQfGI+y}hq<7@Yv(<xFUVsG<A=wTw%}'
        '6k{*y#!)!y5E);XaT9I~XQ<mHGVS7uI}V`8l!RWC^WbJq$^p{?6|;rpmLO+|Frua<`Fdr+2?Dd3i{bVTVdD#rDN*Ijroy-wxB<nR'
        'F1}WUvMNN<FXfkuRn~FLh1&>gg|aGSH6&`OtHL;lr6Q0fXGC0BOanKs8w<GS39BNOTcbi*71C&pB2kr<MluR8<d*VhlvaqMwJn5>'
        '=wlhSG61u_MkX{GjZB|n4%eyCB#bQ;>qz#;Ua;ry@4|uS`3D2<+4jM+-Gjh;`pf>#w!iaiXZPve!25N3uw$g$VqWbOYWPrJp_G>M'
        'l+re(-yJZlT;m)G=?5stYMieE<CF`>N4v>lg`I)z4=f4xHH?E}FVG<$vn@hQ-Y=|3H{@HDMxjE1xlB0N;^479RCaZSa3oQcmB!o|'
        'q%;hiQq3+I=@R^SB>Op{QeD<n>B1H>B5Rl`$3%f>Poe1NYQg-5Xqv<S{M7BAzv%W#HW2X*L`9@~NBy%`UH4_Te{^!xKXT7{{cf+X'
        'dFsnjB|TGBdUByy9y;WACpX(njN@p}nsaLb=-TVr$t*9h#k(O|`Zsy>`1x7?^!iV?`wCTcFOK@BkL;$SI+Hny-qFjhq|ln@yXV*a'
        'i|hWQIa7FnZf&#R7P6_8t}UYo?yzL2_@P!aS^JmQuXQZrvKwpNW5nsO$u!T_hk(t#6F?%jcfTs0iZSGry9RAWGGy^YAqaPPJ2WOv'
        'MHQXC3^VEPG7}aZ?X$g0W!)vdlpDVarsMFjmor|S9<AzI1}B{^9tbXd*mA&%Iqa*k(imlkt%w!wNV74EkfVy;JFb$Y>B|beYM!A~'
        'i(cDXV<%oDsfX>*!Y0XE#yT681}A7eNd%j!S2qMLo9|X_#!cH&>bdnip>)fph~@gO7xk?pH&<9UgF|b{@KZFsntJ9FOWqnboTlI~'
        '9bM<%#uQ@0rZTzQlQ)<PHMoPJ$o%137<HqLzS@IJRfh;vVTN3VMFzYq1`x@1h5}#8FI#P?;G4It<&(66qrsc9lV@||LY)Q+<^;G)'
        'Z~-dKdebFpy7f#<b%<(`l=tnX6MulTWKL>uL__gS9kGtQGC>`d%FbffFpQ36to4riL2e~ImQ8X^LRK2(ngpyg%QXp@8|H%8Pbavb'
        'hJ^?4uhMx9URI);_q8|byq|3ucw754wu15|{~0mOuV!^b_O)y^AZk3`3bhQSTf0+WILD#Kt*_|$C3e%08t=D6PWD!H|F*82*<kMq'
        '?Y-xhOsQ4#N=3y5WoHP?%|3z1PK0@?_LvV3nV5X*hxF}bXfKX}DtL=R;j>?en_sT7=_pUrb{;Rxt`GQ>B`3hbBg&V}*Y={XB!)9Q'
        'Lw+ZbFAElDlHpvO-!5MFPtSWN=e_<vmuLO%pRfDf<MWg5;Z8o;sUfc7&#EWGsZM^>m>-XSoQ}P6wT9$Yq0N%pg6}ycP1kE<cBN?C'
        'EMyk@kvGeuj?FRVSE+iKwMx#LUoX3kQ+x+-Y<qGap=uwQHAE&ou<!JhdA0cbo)Xc$zwk-N0Y^{#U-z`Gk`T7VVu=5-LVl7S(h%%('
        'PVvE2weJ{hA%3q5)jVe3#zah1fMwqRN)Oz}r`_Wh?q&Dt`tSag_5l(9b#>m;!Ma&A^(v3y<=3%g&xli<wU<1ODNP)CX{0DA`~^>E'
        'YySb4lWnp'
    )),
    ('d04a6dc70213d8b549bac30c11cc15eaf0182dea', (
        'c-oazO>f&U488kT5J7>Q<b1E0feuTDVC`XD&?UPDvdlDEZON0Uq-oLrKFN-gG>5J8!GKBnk?-+IiWiu`#L*fRNx=zWb`OM41ei&R'
        'BCV1LV5`mJD%abk;CUVb0NPRM$krbK1rpCV@ugJcp_(wjhUd<=xOjPiUplq1L7^X%e8zZ>5TE@Dudh*5qA8@cQmd+i&{fJNV321~'
        '6p%vv09N-?6`T7e2(l;~@ifOHqZ;aos(Ry;Wu76p)G2bTKa9J>DnqhBKOZZka)iF`=slz>mX@%z@xIO9NCt$exPfDP0$<iB9z(Aa'
        '0;SP}f-r-EOVto3FA!MmjKG87&W3rp2szsk0n0;u9%KVC?Bj@YF-rNkI~w;#8Nd86>~%$N-0NQsQvR`<_6|5(N$cYpgVw8>;Db-N'
        'G{%kR5tlB{mj-`3v=pb@Vr<vEVOKvT_dr0#d9vAQ9F3Khm@t?H_wn4%z4C87DY7Lu7Fk1sd0mkeI>UdK`j%Sfwqvl=R+2WmI%PYD'
        'T{KH7cV`<oT1cyW2mW+;-xOtz{(LA-a&zLS!vr!*-neV;umnD_Q`S3LYc&9N3+xB5>qeN)|4&;@%&I*=>*DL}{AO{zoc^5N&6l&u'
        '{HE0;Ss-;@aX0xk4HdOPkJ;~w`D`(7oe6S!Lu3$ku;sgh|3PWRyhAf5&>Z#fetF+vxVnP2mjT;vb!#W>=nof(d71'
    )),
)

def protected21_workflow_fixtures():
    result = {}
    for oid, encoded in _PROTECTED21_WORKFLOW_BYTES:
        raw = zlib.decompress(base64.b85decode(encoded))
        if gate._blob(raw)["sha"] != oid:
            raise AssertionError("historical21 workflow fixture whole hash differs")
        result[oid] = raw
    return result

class RequiredAndroidTests(unittest.TestCase):
    def setUp(self):
        # Every test supplies its own runner context, never the enclosing CI job's.
        self.enterContext(patch.dict(os.environ, {
            name: value for name, value in os.environ.items() if not name.startswith("GITHUB_")
        }, clear=True))
        self.fixture = ownership.AndroidOwnershipTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.candidate = self.fixture.candidate
        self.temporary = Path(self.fixture.temporary.name)
        self.git = self.fixture.git
        self.policy_root = self.temporary / "policy"
        names = [gate.POLICY, ".github/android-checks.json", ".github/package-workflow-generations.json",
                 ".github/branch-policy.json",
                 "tools/repository-checks/android_gate.py", "tools/repository-checks/check.py",
                 "tools/repository-checks/package_checks.py", gate.CALLEE, *gate.CALLERS,
                 "tools/repository-checks/host_selection.py",
                 *gate.android().EXECUTION_FILES]
        names += [".github/android-owner-transfer.json", "tools/repository-checks/android_handoff.py",
                  "tools/repository-checks/workflows/browser-client.yml", "tools/repository-checks/workflows/browser-direct-client.yml",
                  "tools/repository-checks/workflows/npm-consumers/browser-client.yml"]
        names += [str(path.relative_to(ROOT)) for path in (ROOT / gate.OWNED).rglob("*") if path.is_file()]
        names += [*gate.OWNED_CALLERS, *gate.OWNED_PROJECTS.values()]
        for relative in set(names):
            target = self.policy_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.policy = gate.load_policy()
        self.policy["required_branches"] = ["android-phone"]
        self.policy["activation_blockers"] = []
        self.write_policy()
        self.sequence = 0

    def write_policy(self):
        (self.policy_root / gate.POLICY).write_text(json.dumps(self.policy))

    def workflow_files(self, *, direct=False, producer=False, owned=True, browser=False, protected=False):
        packages = gate.packages()
        name = ("shared-receipt-v1" if producer else "packages-v1") + ("-direct" if direct else "") + "-android"
        if owned:
            name = "protected-producer-seven-target-ci-v1" if protected else "android-owned-npm5-sync-ci-v1"
        generation = next(item for item in packages.workflow_generations() if item["name"] == name)
        paths = list((ROOT / "tools/repository-checks/workflows").rglob("*.yml"))
        contents = {gate._blob(path.read_bytes())["sha"]: path.read_bytes() for path in paths}
        contents[LEGACY_SYNC_BLOB]=legacy_sync_fixture()
        contents.update(protected21_workflow_fixtures())
        if protected:
            # This is the historical21 policy context, not the current future22
            # caller. Preserve its actual trusted bytes as well as its tuple.
            source = self.policy_root / "tools/repository-checks/workflows/producers/repository-checks.yml"
            source.write_bytes(contents[generation['workflows']['.github/workflows/repository-checks.yml']['sha']])
        for relative, entry in generation["workflows"].items():
            target = self.candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[entry["sha"]])
        callee = gate.OWNED + "/android-required.yml" if owned else gate.CALLEE
        (self.candidate / gate.WORKFLOW).write_bytes((ROOT / callee).read_bytes())
        if owned:
            if direct:
                (self.candidate / ".github/workflows/browser-direct-client.yml").write_bytes(
                    (ROOT / "tools/repository-checks/workflows/browser-direct-client.yml").read_bytes())
            transfer = gate.handoff().policy()
            for group in ("legacy_workflows", "source_contracts"):
                for target, item in transfer[group].items():
                    path = self.candidate / target
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((ROOT / item["source"]).read_bytes())
                    path.chmod(0o755 if item["mode"] == "100755" else 0o644)
            profile = {"schema": 1, "platform": "android", "suites": transfer["profiles"]["android-phone"]["required_suites"]}
            path = self.candidate / "tests/platform-profile.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(profile))
            for item in profile["suites"]:
                entrypoint = self.candidate / item["entrypoint"]
                if not entrypoint.exists():
                    entrypoint.parent.mkdir(parents=True, exist_ok=True)
                    entrypoint.write_text("# Profile fixture.\n")
        self.fixture.commit()
        return generation

    def merge(self, relative="android/phone/changed.cpp", contents="// changed\n", *, empty=False, mode=None, rename_from=None,
              additional=None):
        base = self.git("rev-parse", "HEAD")
        self.sequence += 1
        task = "task" + str(self.sequence)
        self.git("checkout", "-qb", task)
        if empty:
            self.git("commit", "--allow-empty", "-qm", "Empty source delta")
        else:
            path = self.candidate / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if rename_from is not None:
                (self.candidate / rename_from).rename(path)
            elif mode == "gitlink":
                self.git("update-index", "--add", "--cacheinfo", "160000," + base + "," + relative)
            elif mode == "symlink":
                path.unlink(missing_ok=True)
                path.symlink_to("outside")
            elif contents is None:
                path.unlink()
            else:
                path.write_text(contents)
                if mode is not None: path.chmod(mode)
            for name, value in (additional or {}).items():
                extra = self.candidate / name
                extra.parent.mkdir(parents=True, exist_ok=True)
                extra.write_text(value)
            if mode == "gitlink":
                self.git("commit", "-qm", "Foreign gitlink fixture")
            else:
                self.fixture.commit()
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "android-phone")
        self.git("merge", "--no-ff", "-qm", "Exact candidate fixture", task)
        sha = self.git("rev-parse", "HEAD")
        repository = {"full_name": gate.REPOSITORY, "id": gate.REPOSITORY_ID}
        self.event = {"repository": repository, "pull_request": {
            "base": {"ref": "android-phone", "sha": base, "repo": repository},
            "head": {"ref": "task/android/change", "sha": head, "repo": repository}}}
        self.sha = sha
        return self.plan()

    def plan(self, **kwargs):
        return gate.candidate_plan(self.candidate, self.event, self.sha, policy_root=self.policy_root, **kwargs)

    def anchor(self):
        self.policy["reviewed_sources"]["android-phone"]["readers"] = gate.reader_identity(gate._sources(self.candidate).entries)
        self.write_policy()

    def lock_sources(self):
        """Actual reviewed package trees and caller wiring; no npm execution."""
        self.workflow_files()
        packages = gate.packages()
        archive = subprocess.check_output([
            "git", "archive", "--format=tar", "HEAD", "--", packages.BROWSER, packages.S3,
        ], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            for member in contents:
                destination = self.candidate / member.name
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    self.assertTrue(member.isfile())
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(contents.extractfile(member).read())
                    destination.chmod(member.mode)
        consumers = packages.load("android_lock_fixture_consumers", "tools/repository-checks/npm_consumers.py")
        self.consumer_policies = consumers.PROJECTS
        for project, policy in self.consumer_policies.items():
            target = self.candidate / project / "package-lock.json"
            value = json.loads(target.read_text())
            value["packages"][policy["node"]] = policy["old"]
            target.write_text(json.dumps(value) + "\n")
        (self.candidate / gate.POLICY).write_bytes((ROOT / gate.POLICY).read_bytes())
        self.fixture.commit()

    def lock_anchor(self):
        sources = gate._sources(self.candidate)
        self.policy["reviewed_lock_sources"]["android-phone"] = {
            "commit": self.git("rev-parse", "HEAD"), "tree": self.git("rev-parse", "HEAD^{tree}"),
            "readers": gate.lock_reader_identity(sources.entries),
            "entries": len(sources.entries) - len(gate.FOREIGN_LOCKS),
        }
        self.write_policy()

    def updated_lock(self, relative, *, unsupported=False, formatting=False):
        value = json.loads((self.candidate / relative).read_text())
        if not formatting:
            policy = self.consumer_policies[str(Path(relative).parent)]
            value["packages"][policy["node"]] = deepcopy(policy["new"])
            if unsupported:
                value["packages"][policy["node"]]["version"] = "99.0.0"
        return json.dumps(value, indent=4) + "\n"

    def test_exact_pr_selects_forty_distinct_owners_and_all_current_phone_cases(self):
        result = self.merge()
        self.assertTrue(result["required"])
        self.assertEqual(result["views"], list(ownership.android.VIEWS))
        owner = gate.android().plan(self.candidate, "android-phone", views=result["views"])
        self.assertEqual(len(owner["executions"]), 40)
        self.assertEqual(len(owner["executions"]["phone-robolectric-launcher"]["cases"]), 116)
        self.assertIn("critical-policy-mutations", owner["executions"])
        self.assertEqual(result["owner_plan"], owner["plan"])
        self.assertNotIn("shared", owner["executions"])

    def test_parent_sync_and_reconcile_names_never_waive_critical_mutation(self):
        self.merge()
        for name in ("main", "android-main", "reconcile/android-phone/current", "feature/android-phone/current"):
            self.event["pull_request"]["head"]["ref"] = name
            self.assertIn("mutation", self.plan()["views"])
            self.assertTrue(self.plan()["required"])

    def test_forged_event_candidate_parent_target_and_foreign_repository_fail(self):
        self.merge()
        for mutate in (lambda e: e["repository"].update(id=1),
                       lambda e: e["pull_request"]["base"].update(sha="a" * 40),
                       lambda e: e["pull_request"]["head"].update(sha="b" * 40),
                       lambda e: e["pull_request"]["base"]["repo"].update(full_name="overte-org/overte")):
            event = deepcopy(self.event)
            mutate(event)
            with self.assertRaises(ValueError):
                gate.candidate_plan(self.candidate, event, self.sha, policy_root=self.policy_root)
        with self.assertRaises(ValueError):
            gate.candidate_plan(self.candidate, self.event, "c" * 40, policy_root=self.policy_root)
        with self.assertRaises(ValueError):
            self.plan(event_name="push")
        self.event["pull_request"]["base"]["ref"] = "unknown-target"
        with self.assertRaises(ValueError): self.plan()
        self.event["pull_request"]["base"]["ref"] = "android-phone"
        (self.candidate / "android/common/tests/suite/catalog.json").write_text("dirty")
        with self.assertRaises(ValueError): self.plan()

    def test_independent_browser_delta_requires_both_full_reader_anchors_and_regular_modes(self):
        self.anchor()
        result = self.merge("browser-client/src/example.ts", "export const x=1;\n")
        self.assertFalse(result["required"])
        self.assertEqual(result["reason"], "reviewed-independent-inputs")
        self.assertEqual(result["views"], [])
        sparse = self.fixture.sparse_clone()
        self.assertEqual(gate.candidate_plan(sparse, self.event, self.sha, policy_root=self.policy_root), result)
        self.policy["reviewed_sources"]["android-phone"]["readers"] = "sha256:" + "0" * 64
        self.write_policy()
        self.assertTrue(self.plan()["required"])

    def test_historical_reader_change_then_browser_change_cannot_use_old_anchor(self):
        self.anchor()
        reader = self.candidate / "android/common/tests/new-reader.py"
        reader.write_text("# now observes browser assets\n")
        self.fixture.commit()
        self.assertTrue(self.merge("browser-client/asset.txt", "changed")["required"])

    def test_exact_lock_updates_recompute_actual_mandatory_npm_owners(self):
        self.lock_sources()
        self.lock_anchor()
        for path, formatting in (("browser-client/package-lock.json", True),
                                 ("browser-client/package-lock.json", False),
                                 ("script-archive/marketplace/S3Server/package-lock.json", False)):
            with self.subTest(path=path, formatting=formatting):
                result = self.merge(path, self.updated_lock(path, formatting=formatting))
                self.assertFalse(result["required"])
                self.assertEqual(result["reason"], "reviewed-package-lock-inputs")
                self.assertEqual(result["views"], [])
                expected = gate.packages().candidate_plan(self.candidate, self.event, self.sha)
                self.assertEqual(result["lock_package_plan"], expected["plan"])
                selected = expected["dependency_profiles"]["projects"][str(Path(path).parent)]
                self.assertEqual(selected["required"], not formatting)
                sparse = self.fixture.sparse_clone("lock-sparse-" + str(self.sequence))
                self.assertEqual(gate.candidate_plan(sparse, self.event, self.sha, policy_root=self.policy_root), result)

    def test_two_lock_delta_retains_both_separate_package_owners(self):
        self.lock_sources()
        self.lock_anchor()
        browser, s3 = "browser-client/package-lock.json", "script-archive/marketplace/S3Server/package-lock.json"
        result = self.merge(browser, self.updated_lock(browser), additional={s3: self.updated_lock(s3)})
        self.assertFalse(result["required"])
        package = gate.packages().candidate_plan(self.candidate, self.event, self.sha)
        self.assertEqual(set(package["package_set"]), {"browser-client", "script-archive/marketplace/S3Server"})
        self.assertEqual(result["lock_package_plan"], package["plan"])

    def test_lock_reader_projection_binds_every_other_root_and_policy_membership(self):
        self.lock_sources()
        original = gate._sources(self.candidate).entries
        expected = gate.lock_reader_identity(original)
        policy_bytes = deepcopy(original)
        policy_bytes[gate.POLICY]["sha"] = "e" * 40
        self.assertEqual(gate.lock_reader_identity(policy_bytes), expected)
        for relative in (*[root + "new-reader.py" for root in gate.INDEPENDENT_ROOTS],
                         "android/common/tests/javascript/package-lock.json", "package.json",
                         "scripts/new-lock-reader.js", "tests/new-lock-reader.py"):
            changed = deepcopy(original)
            changed[relative] = gate._blob(b"new consumer\n")
            with self.subTest(relative=relative):
                self.assertNotEqual(gate.lock_reader_identity(changed), expected)
        for mode in (None, "100755", "120000", "160000"):
            changed = deepcopy(original)
            if mode is None:
                del changed[gate.POLICY]
            else:
                changed[gate.POLICY].update(mode=mode, type="commit" if mode == "160000" else "blob")
            with self.subTest(policy_mode=mode), self.assertRaises(ValueError):
                gate.lock_reader_identity(changed)
        before = gate._policy_identity(self.policy_root)
        self.policy["required_branches"] = []
        self.write_policy()
        self.assertNotEqual(gate._policy_identity(self.policy_root), before)

    def test_lock_omission_requires_new_anchor_and_hermetic_base_without_old_root_fallthrough(self):
        self.lock_sources()
        self.anchor()  # A legacy Browser-root anchor cannot authorize this route.
        browser = "browser-client/package-lock.json"
        self.assertTrue(self.merge(browser, self.updated_lock(browser))["required"])
        old = legacy_metadata_fixture()
        self.assertEqual(gate.handoff().policy()["source_contracts"][gate.HERMETIC_METADATA_TEST]["reviewed_blob"],
                         LEGACY_METADATA_BLOB)
        (self.candidate / gate.HERMETIC_METADATA_TEST).write_bytes(old)
        self.fixture.commit()
        self.assertEqual(self.git("rev-parse", "HEAD:" + gate.HERMETIC_METADATA_TEST), LEGACY_METADATA_BLOB)
        self.lock_anchor()  # Even a matching anchor cannot review the old archive reader.
        self.anchor()
        result = self.merge(browser, (self.candidate / browser).read_text() + "\n")
        self.assertTrue(result["required"])
        self.assertIsNone(result["lock_package_plan"])

    def test_full_foreign_package_requires_actual_selected_job_before_android_omission(self):
        self.lock_sources()
        base=self.git("rev-parse","HEAD")
        for path,malformed in (("browser-client/package-lock.json",False),
                ("script-archive/marketplace/S3Server/package-lock.json",False),
                ("browser-client/package-lock.json",True)):
            self.git("reset","--hard",base);self.lock_anchor()
            contents='{"unexpected":true}\n' if malformed else self.updated_lock(path,unsupported=True)
            result=self.merge(path,contents)
            package=gate.packages().candidate_plan(self.candidate,self.event,self.sha)
            project=str(Path(path).parent)
            with self.subTest(path=path,malformed=malformed):
                selected=package["dependency_profiles"]["projects"][project]
                self.assertEqual(selected["profile"],"full");self.assertTrue(selected["required"])
                if project not in package["package_set"]:
                    # The historical full Browser workflow has no bound
                    # required package result here. Its profile alone cannot
                    # waive Android; wiring that full owner remains separate.
                    self.assertTrue(result["required"])
                    self.assertIsNone(result["lock_package_plan"])
                    continue
                self.assertFalse(result["required"]);self.assertEqual(result["views"],[])
                self.assertEqual(result["lock_package_plan"],package["plan"])
                missing=deepcopy(package);missing["package_set"]=[]
                packages=gate.packages()
                with patch.object(gate,"packages",return_value=packages), \
                        patch.object(packages,"candidate_plan",return_value=missing):
                    self.assertTrue(self.plan()["required"])

    def test_nonordinary_lock_entries_and_missing_inputs_keep_complete_union(self):
        self.lock_sources()
        base = self.git("rev-parse", "HEAD")
        browser = "browser-client/package-lock.json"
        supported = self.updated_lock(browser)
        for mutation in ("mode", "symlink", "delete", "missing-base", "executable-base"):
            with self.subTest(mutation=mutation):
                self.git("reset", "--hard", base)
                target = self.candidate / browser
                if mutation == "missing-base":
                    target.unlink()
                    self.fixture.commit()
                elif mutation == "executable-base":
                    target.chmod(0o755)
                    self.fixture.commit()
                self.lock_anchor()
                self.anchor()
                contents, mode = supported, None
                if mutation == "mode": mode = 0o755
                elif mutation == "symlink": mode = "symlink"
                elif mutation == "delete": contents = None
                elif mutation == "executable-base": mode = 0o644
                result = self.merge(browser, contents, mode=mode)
                self.assertTrue(result["required"])
                self.assertIsNone(result["lock_package_plan"])
                self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=result["views"])["executions"]), 40)

    def test_lock_plus_policy_consumer_or_ancestor_changes_keep_complete_union(self):
        self.lock_sources()
        self.lock_anchor()
        self.anchor()
        base = self.git("rev-parse", "HEAD")
        browser = "browser-client/package-lock.json"
        for relative in (gate.POLICY, "browser-client/new-consumer.js", "package.json",
                         "android/common/tests/javascript/package-lock.json"):
            with self.subTest(relative=relative):
                self.git("reset", "--hard", base)
                value = (self.candidate / gate.POLICY).read_text() + "\n" if relative == gate.POLICY else "{}\n"
                result = self.merge(browser, self.updated_lock(browser), additional={relative: value})
                self.assertTrue(result["required"])
                self.assertIsNone(result["lock_package_plan"])

    def test_historical_reader_or_other_npm_graph_difference_cannot_use_lock_anchor(self):
        self.lock_sources()
        self.lock_anchor()
        base = self.git("rev-parse", "HEAD")
        browser = "browser-client/package-lock.json"
        for relative in ("tools/issue-intake/new-lock-reader.py", "scripts/new-lock-reader.js",
                         "browser-client/new-consumer.js"):
            with self.subTest(relative=relative):
                self.git("reset", "--hard", base)
                target = self.candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# historical difference outside the event delta\n")
                self.fixture.commit()
                self.assertTrue(self.merge(browser, self.updated_lock(browser))["required"])

    def test_lock_only_diagnostics_and_manual_events_retain_extended_inventories(self):
        self.lock_sources()
        self.lock_anchor()
        browser = "browser-client/package-lock.json"
        self.assertFalse(self.merge(browser, self.updated_lock(browser))["required"])
        self.event["pull_request"]["labels"] = [{"name": "android-long-diagnostics"}]
        labelled = self.plan()
        self.assertTrue(labelled["required"])
        self.assertIsNone(labelled["lock_package_plan"])
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=labelled["views"])["executions"]), 45)
        event = {"repository": self.event["repository"], "ref": "refs/heads/android-phone"}
        manual = gate.candidate_plan(self.candidate, event, self.sha, event_name="workflow_dispatch", policy_root=self.policy_root)
        self.assertTrue(manual["required"])
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=manual["views"])["executions"]), 45)
        complete = list(gate.android().VIEWS) + list(gate.android().DIAGNOSTIC_VIEWS)
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=complete)["executions"]), 46)

    def test_lock_omission_rejects_recomputed_package_identity_and_owner_tampering(self):
        self.lock_sources()
        self.lock_anchor()
        browser = "browser-client/package-lock.json"
        self.assertFalse(self.merge(browser, self.updated_lock(browser))["required"])
        packages = gate.packages()
        expected = packages.candidate_plan(self.candidate, self.event, self.sha)
        for mutation in ("candidate", "base", "head", "tree", "paths", "unknown", "regular", "owner", "generation"):
            changed = deepcopy(expected)
            if mutation in ("candidate", "base", "head", "tree"): changed[mutation] = "c" * 40
            elif mutation == "paths": changed["paths"] = []
            elif mutation in ("unknown", "regular"): changed[mutation] = mutation == "unknown"
            elif mutation == "owner": changed["package_set"] = []
            else: changed["consumer_generation"] = False
            with self.subTest(mutation=mutation), patch.object(gate, "packages", return_value=packages), \
                    patch.object(packages, "candidate_plan", return_value=changed):
                self.assertTrue(self.plan()["required"])
        (self.candidate / browser).write_text("dirty working tree\n")
        with self.assertRaises(ValueError): self.plan()

    def test_real_deletion_and_rename_keep_both_change_sides(self):
        self.anchor()
        self.assertFalse(self.merge("browser-client/deleted.txt", "browser fixture")["required"])
        deleted = self.merge("browser-client/deleted.txt", None)
        self.assertFalse(deleted["required"])
        self.assertEqual(deleted["paths"], ["browser-client/deleted.txt"])
        self.assertFalse(self.merge("browser-client/rename.txt", "browser fixture")["required"])
        renamed = self.merge("scripts/packaged.md", rename_from="browser-client/rename.txt")
        self.assertTrue(renamed["required"])
        self.assertEqual(renamed["paths"], ["browser-client/rename.txt", "scripts/packaged.md"])

    def test_packaged_markdown_unknown_and_ancestor_package_inputs_stay_complete(self):
        self.anchor()
        for relative in ("BUILD_ANDROID.md", "scripts/packaged.md", "package.json", "new-root-file"):
            with self.subTest(relative=relative):
                self.assertTrue(self.merge(relative, "new immutable input")["required"])
        # Even an unrelated subsequent delta cannot hide a historical new reader.
        self.assertTrue(self.merge("browser-client/asset.txt", "browser fixture")["required"])

    def test_symlink_and_gitlink_in_independent_root_never_receive_skip(self):
        self.anchor()
        self.assertTrue(self.merge("browser-client/unsafe", mode="symlink")["required"])
        self.assertTrue(self.merge("browser-client/foreign", mode="gitlink")["required"])

    def test_verified_empty_and_manual_variants_preserve_existing_meaning(self):
        result = self.merge(empty=True)
        self.assertFalse(result["required"])
        self.assertEqual(result["reason"], "verified-empty-tree-delta")
        event = {"repository": self.event["repository"], "ref": "refs/heads/android-phone"}
        manual = gate.candidate_plan(self.candidate, event, self.sha, event_name="workflow_dispatch", policy_root=self.policy_root)
        self.assertTrue(manual["required"])
        self.assertEqual(manual["views"], list(ownership.android.DEFAULT_VIEWS) + list(ownership.android.DIAGNOSTIC_VIEWS))
        self.assertNotIn("mutation", manual["views"])
        self.assertNotIn("stability", result["views"])
        self.assertNotIn("endurance", result["views"])

    def test_complete_old_and_new_package_tuples_remain_approved_but_mixed_android_callee_fails(self):
        for direct, producer in ((False, False), (False, True), (True, False), (True, True)):
            generation = self.workflow_files(direct=direct, producer=producer, owned=False)
            self.assertEqual(gate.validate_tree_wiring(gate._sources(self.candidate).entries), generation["name"])
        original = deepcopy(gate._sources(self.candidate).entries)
        for mutate in (lambda t: t.pop(gate.WORKFLOW),
                       lambda t: t[gate.WORKFLOW].update(mode="100755"),
                       lambda t: t[gate.WORKFLOW].update(mode="120000"),
                       lambda t: t[gate.WORKFLOW].update(type="commit", mode="160000"),
                       lambda t: t[gate.WORKFLOW].update(sha="a" * 40),
                       lambda t: t[".github/workflows/repository-checks.yml"].update(sha="b" * 40)):
            tree = deepcopy(original)
            mutate(tree)
            with self.assertRaises(ValueError): gate.validate_tree_wiring(tree)

    def test_protected_producer_pair_is_additive_and_rejects_mixed_or_foreign_controls(self):
        old = self.workflow_files()
        self.assertEqual(gate.validate_tree_wiring(gate._sources(self.candidate).entries, policy_root=self.policy_root), old['name'])
        # Retain the exact historical five-file tuple; the current canonical
        # producer is its separate six-file metadata successor.
        packages = gate.packages()
        prior = next(row for row in packages.workflow_generations() if row['name']=='protected-producer-ci37-v1')
        self.assertEqual(packages.validate_tree_wiring(prior['workflows']),prior['name'])
        self.assertEqual(len(prior['workflows']),5)
        generation = self.workflow_files(protected=True)
        self.assertEqual(set(generation['workflows']),set(packages.METADATA_WORKFLOW_PATHS))
        self.assertEqual(len(generation['workflows']),6)
        entries = gate._sources(self.candidate).entries
        self.assertEqual(gate.validate_tree_wiring(entries, policy_root=self.policy_root), generation['name'])
        gate.validate_owned_generation(self.candidate, 'android-phone', policy_root=self.policy_root)
        self.assertTrue(gate.has_staged_caller(self.candidate, policy_root=self.policy_root))
        for path in generation['workflows']:
            missing = deepcopy(entries)
            del missing[path]
            with self.subTest(missing=path), self.assertRaises(ValueError):
                gate.validate_tree_wiring(missing,policy_root=self.policy_root)
        for path in ('.github/workflows/repository-checks.yml', '.github/workflows/project-tests.yml'):
            for replacement in (old['workflows'][path], {'mode': '100644', 'type': 'blob', 'sha': 'a' * 40},
                                {**generation['workflows'][path], 'mode': '100755'},
                                {**generation['workflows'][path], 'mode': '120000'}):
                mixed = deepcopy(entries)
                mixed[path] = replacement
                with self.subTest(path=path, replacement=replacement), self.assertRaises(ValueError):
                    gate.validate_tree_wiring(mixed, policy_root=self.policy_root)
        for field, value in (('caller', 'foreign/repository-checks.yml'),
                             ('project', gate.OWNED + '/project-tests.yml')):
            changed = deepcopy(self.policy)
            prospective = next(g for g in changed['workflow_generations']
                if g['caller'] == 'tools/repository-checks/workflows/producers/repository-checks.yml')
            prospective[field] = value
            (self.policy_root / gate.POLICY).write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.load_policy(self.policy_root)
            self.write_policy()
        baseline = gate._policy_identity(self.policy_root)
        prospective = next(g for g in self.policy['workflow_generations']
            if g['caller'] == 'tools/repository-checks/workflows/producers/repository-checks.yml')
        for name in ('caller', 'project'):
            path = self.policy_root / prospective[name]
            body = path.read_bytes()
            path.write_bytes(body + b'\n')
            with self.subTest(identity=name):
                self.assertNotEqual(gate._policy_identity(self.policy_root), baseline)
            path.write_bytes(body)
        self.assertFalse(gate.ACTIVATION_READY)
        self.assertEqual(gate.load_policy()['required_branches'], [])

    def test_default_policy_explicitly_blocks_live_admission_and_candidate_cannot_enable_it(self):
        self.workflow_files()
        self.merge()
        self.assertTrue(gate.has_staged_caller(self.candidate))
        with self.assertRaisesRegex(ValueError, "activation blocked"):
            gate.admit(self.candidate, self.event)
        # Trusted test policy enables only the fake fixture target.
        with self.assertRaisesRegex(ValueError, "not qualified"):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)
        with patch.object(gate, "ACTIVATION_READY", True):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)
        self.policy["activation_blockers"] = ["extended-tier-prerequisite-transfer"]
        self.write_policy()
        with self.assertRaisesRegex(ValueError, "extended-tier-prerequisite-transfer"):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)

    def test_untrusted_candidate_flags_and_corrupt_trusted_policy_cannot_authorize_activation(self):
        self.workflow_files()
        candidate_policy = self.candidate / gate.POLICY
        candidate_policy.write_text(json.dumps(self.policy))
        self.fixture.commit()
        self.merge()
        with self.assertRaisesRegex(ValueError, "activation blocked"):
            gate.admit(self.candidate, self.event)
        for mutate in (lambda p: p["activation_blockers"].append("unknown"),
                       lambda p: p["required_branches"].append("unknown"),
                       lambda p: p["independent_roots"].append("scripts/"),
                       lambda p: p["reviewed_lock_sources"].pop("android-vr"),
                       lambda p: p["reviewed_lock_sources"]["android-phone"].update(entries=True),
                       lambda p: p["reviewed_lock_sources"]["android-phone"].update(readers="sha256:unknown"),
                       lambda p: p["workflow_generations"].append(deepcopy(p["workflow_generations"][0]))):
            value = deepcopy(self.policy)
            mutate(value)
            (self.policy_root / gate.POLICY).write_text(json.dumps(value))
            with self.assertRaises(ValueError): gate.load_policy(self.policy_root)
        self.write_policy()
        before = self.plan()["policy"]
        helper = self.policy_root / "tools/repository-checks/android-host-prepare.sh"
        helper.write_text(helper.read_text() + "# reviewed preparation change\n")
        self.assertNotEqual(self.plan()["policy"], before)

    def test_inner_and_outer_recompute_results_and_reject_skips_failures_omissions_tampering(self):
        expected = self.merge()
        route = {"result": "success", "outputs": gate.outputs(expected)}
        executed = {"result": "success", "outputs": gate.receipt(expected)}
        needs = {"route": route, "execute": executed}
        self.assertEqual(gate.verify_inner(needs, expected), gate.receipt(expected))
        for change in (lambda n: n.pop("execute"), lambda n: n["route"].update(result="failure"),
                       lambda n: n["execute"].update(result="skipped"),
                       lambda n: n["execute"].update(result="failure"),
                       lambda n: n["execute"]["outputs"].update(inventory="sha256:" + "a" * 64),
                       lambda n: n["route"]["outputs"].update(android_plan="sha256:" + "b" * 64),
                       lambda n: n["execute"]["outputs"].update(candidate="c" * 40)):
            altered = deepcopy(needs)
            change(altered)
            with self.assertRaises(ValueError): gate.verify_inner(altered, expected)
        # The required outer aggregate cannot silently omit its Android owner.
        baseline = {name: {"result": "skipped"} for name in ("project", "workflow-security", "native")}
        baseline.update(route={"result": "success", "outputs": {"mode": "documentation", "security": "false", "native": "skip", **gate.outputs(expected)}},
                        documentation={"result": "success"}, android=executed)
        self.assertEqual(checks.verify(baseline, require_native=False, android_plan=expected, require_android=True)["status"], "PASS")
        del baseline["android"]
        with self.assertRaises(ValueError): checks.verify(baseline, require_native=False, android_plan=expected, require_android=True)

    def test_real_trusted_controller_runs_complete_union_once_and_requires_all_cases(self):
        self.workflow_files()
        expected = self.merge()
        self.fixture.active_items = gate.android().plan(self.candidate, "android-phone", views=expected["views"])["executions"]
        with patch.object(gate, "ACTIVATION_READY", True), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = gate.run(self.candidate, self.event, self.sha, event_name="pull_request", policy_root=self.policy_root,
                receipt_path=self.temporary / "execution.json", reports=self.temporary / "reports",
                expected_outputs=gate.outputs(expected), run_command=self.fixture.run_command, capture=ownership.runtime)
        self.assertEqual(result, gate.receipt(expected))
        self.assertEqual(len(self.fixture.calls), 40)
        self.assertEqual(len(set(self.fixture.calls)), 40)
        actual = json.loads((self.temporary / "execution.json").read_text())
        self.assertEqual(len(actual["executions"]["phone-robolectric-launcher"]["cases"]), 116)
        self.assertEqual(actual["conclusion"], "success")
        tampered = gate.outputs(expected) | {"android_inventory": "sha256:" + "0" * 64}
        with patch.object(gate, "ACTIVATION_READY", True), self.assertRaises(ValueError):
            gate.run(self.candidate, self.event, self.sha, event_name="pull_request", policy_root=self.policy_root,
                receipt_path=self.temporary / "bad.json", reports=self.temporary / "bad", expected_outputs=tampered)

    def test_deleted_current_phone_focus_class_cannot_reduce_mandatory_inventory(self):
        path = self.candidate / "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/PhoneEmbeddedWebFocusRobolectricTest.java"
        path.unlink()
        self.fixture.commit()
        with self.assertRaisesRegex(ValueError, "missing"):
            gate.android().plan(self.candidate, "android-phone", views=["coverage"])

    def test_pinned_quality_tools_use_only_external_trusted_layout_and_effective_context(self):
        runtime = gate.android()._shared()[1]
        venv = self.temporary / "venv"
        quality = venv / "overte-static-quality"
        for relative, version in (("bin/shellcheck", "ShellCheck - shell script analysis tool\nversion: 0.11.0"),
                                  ("ruff-venv/bin/ruff", "ruff 0.15.22")):
            path = quality / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/sh\nprintf '%s\\n' '" + version + "'\n")
            path.chmod(0o755)
        owner = gate.android()
        with patch.object(owner.sys, "prefix", str(venv)):
            identity = owner._quality_identity(runtime)
            self.assertEqual(identity["ruff"]["version"], "ruff 0.15.22")
            with patch.dict(os.environ, {"OVERTE_STATIC_QUALITY_TOOLS_DIR": "/candidate/evil"}):
                with owner.process_environment(self.temporary / "report"):
                    self.assertEqual(os.environ["OVERTE_STATIC_QUALITY_TOOLS_DIR"], str(quality))
                self.assertEqual(os.environ["OVERTE_STATIC_QUALITY_TOOLS_DIR"], "/candidate/evil")
            (quality / "bin/shellcheck").write_text("#!/bin/sh\nprintf 'version: 0.10.0\\n'\n")
            with self.assertRaises(ValueError): owner._quality_identity(runtime)
        for name in ("quality", "gcovr"):
            identity = ownership.runtime()
            del identity[name]
            with self.assertRaises(ValueError): owner.validate_environment(identity)

    def test_canonical_workflow_routes_before_setup_and_runs_only_trusted_full_union(self):
        template = (ROOT / gate.CALLEE).read_text()
        value = yaml.safe_load(template)
        jobs = value["jobs"]
        self.assertEqual(set(jobs), {"route", "execute", "verify"})
        self.assertEqual(jobs["execute"]["if"], "needs.route.outputs.android_required == 'true'")
        self.assertEqual(jobs["verify"]["if"], "always()")
        self.assertEqual(jobs["verify"]["needs"], ["route", "execute"])
        self.assertNotIn("setup-", json.dumps(jobs["route"]))
        self.assertNotIn("setup-", json.dumps(jobs["verify"]))
        self.assertIn("java-version: 21", template)
        self.assertIn("node-version: 22", template)
        self.assertIn('android-host-prepare.sh "$RUNNER_TEMP/android-host-venv"', template)
        self.assertIn('"$RUNNER_TEMP/android-host-venv/bin/python" trusted/tools/repository-checks/android_gate.py run', template)
        self.assertNotIn("./candidate/", template)
        self.assertNotIn("continue-on-error", template)
        for step in jobs["execute"]["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                self.assertFalse(step["with"]["persist-credentials"])
        prepare = (ROOT / "tools/repository-checks/android-host-prepare.sh").read_text()
        self.assertIn("gcovr==8.4", prepare)
        self.assertIn("--require-hashes", prepare)
        self.assertIn("sha256sum --check --status", prepare)
        self.assertNotIn("candidate", "\n".join(line for line in prepare.splitlines() if not line.startswith("#")))




class CurrentAndroidNativeOwnerTests(unittest.TestCase):
    """Fake native API; no Android commands, tool capture or host qualification."""
    def setUp(self):
        _,_,A,_=gate._native_modules()
        self.A=A
        self.sha='3'*40;self.head='2'*40;self.base='1'*40;self.default='4'*40
        self.now=datetime(2026,10,16,20,0,tzinfo=timezone.utc)
        repo={'full_name':gate.REPOSITORY,'id':gate.REPOSITORY_ID}
        self.binding={'repository':gate.REPOSITORY,'repository_id':gate.REPOSITORY_ID,'pull_request':17,
            'head_repository_id':gate.REPOSITORY_ID,'base_ref':'android-phone','base_sha':self.base,
            'head_ref':'fix/android/fixture','head_sha':self.head,'merge_sha':self.sha,
            'merge_tree':'5'*40,'merge_parents':[self.base,self.head]}
        self.event={'number':17,'repository':repo,'pull_request':{'number':17,'labels':[],
            'base':{'ref':'android-phone','sha':self.base,'repo':repo},
            'head':{'ref':'fix/android/fixture','sha':self.head,'repo':repo}}}
        self.environment={'GITHUB_RUN_ID':'100','GITHUB_RUN_ATTEMPT':'1'}
        self.expected={'required':True,'candidate':self.sha,'target':'android-phone',
            'views':['fast','contracts','coverage','android-vr','pico','mutation'],
            'plan':'sha256:'+'a'*64,'inventory':'sha256:'+'b'*64,'owner_plan':'sha256:'+'c'*64}
        self.needs={'android':{'result':'success','outputs':gate.receipt(self.expected)}}
        self.current={gate.WORKFLOW:{'mode':'100644','type':'blob','sha':'a'*40}}
        self.source=(self.binding,{'default':self.default},self.current,{}, {'trusted':'D source boundary'})
        self.run={'id':100,'workflow_id':99,'check_suite_id':200,'path':'.github/workflows/repository-checks.yml',
            'event':'pull_request','head_sha':self.head,'head_branch':self.binding['head_ref'],
            'run_attempt':1,'status':'in_progress','conclusion':None,
            'run_started_at':'2026-10-16T19:00:00Z','updated_at':'2026-10-16T19:30:00Z',
            'repository':repo,'head_repository':repo,'pull_requests':[{'number':17}],
            'referenced_workflows':[{'path':gate.REPOSITORY+'/'+gate.WORKFLOW+'@'+self.sha,
                'sha':self.sha,'ref':'refs/pull/17/merge'}]}
        self.listed=[deepcopy(self.run)];self.attempt=deepcopy(self.run)
        self.jobs=[];self.checks={}
        for index,(name,step) in enumerate(gate.CURRENT_JOBS.items()):
            start='2026-10-16T19:'+str(index*5+1).zfill(2)+':00Z'
            end='2026-10-16T19:'+str(index*5+3).zfill(2)+':00Z'
            identity=300+index
            job={'id':identity,'run_id':100,'run_attempt':1,'head_sha':self.head,
                'name':name,'status':'completed','conclusion':'success','started_at':start,'completed_at':end,
                'check_run_url':f'https://api.github.com/repos/{gate.REPOSITORY}/check-runs/{identity}',
                'steps':[{'name':step,'status':'completed','conclusion':'success','started_at':start,'completed_at':end}]}
            self.jobs.append(job)
            self.checks[identity]={'id':identity,'head_sha':self.head,'check_suite':{'id':200},'app':{'id':15368},
                **{key:job[key] for key in ('name','status','conclusion','started_at','completed_at')}}
        self.outer={'id':399,'run_id':100,'run_attempt':1,'head_sha':self.head,
            'name':'repository-checks','status':'in_progress','conclusion':None,
            'started_at':'2026-10-16T19:20:00Z','completed_at':None,
            'check_run_url':f'https://api.github.com/repos/{gate.REPOSITORY}/check-runs/399','steps':[]}
        self.jobs.append(deepcopy(self.outer))
        self.checks[399]={'id':399,'head_sha':self.head,'check_suite':{'id':200},'app':{'id':15368},
            **{key:self.outer[key] for key in ('name','status','conclusion','started_at','completed_at')}}
        self.registration={'id':99,'path':'.github/workflows/repository-checks.yml','state':'active'}
        def get(endpoint):
            if endpoint.startswith(A.PREFIX+'/'):endpoint=endpoint[len(A.PREFIX)+1:]
            return deepcopy(self.object(endpoint))
        self.adapter=A.Adapter(SimpleNamespace(json=get))
        self.adapter._pages=lambda endpoint,field,**kwargs:deepcopy(self.listed if field=='workflow_runs' else self.jobs)
        self.metadata=self.enterContext(patch.object(self.adapter,'metadata_observation',return_value=None))
        # The future shared adapter owns this authenticated-type projection.
        # Its independent tests validate source/row identities; this fixture
        # proves the Android consumer forwards the complete fresh API record.
        def inventory(row,observation):
            return ({'native_nonproducer_intent':observation}
                if type(observation) is dict and observation.get('kind')=='authenticated-metadata-nonproducer-intent'
                else row)
        self.inventory=self.enterContext(patch.object(A,'metadata_inventory_record',side_effect=inventory,create=True))
        self.owner=gate.android()
        self.normal=self.owner.load_policy()['views']
        names=dict.fromkeys(proof['execution'] for view in self.expected['views'] for proof in self.normal[view].values())
        self.assertEqual(len(names),40)
        self.owner_plan={'plan':self.expected['owner_plan'],'executions':{name:{} for name in names}}
        self.stack=self.enterContext(__import__('contextlib').ExitStack())
        self.stack.enter_context(patch.object(gate,'SOURCE_CAPABILITY',True))
        self.bootstrap=self.stack.enter_context(patch.object(gate,'_protected_default',return_value={'default':self.default}))
        self.stack.enter_context(patch.object(gate,'_current_metadata_policy',return_value=SimpleNamespace(trusted='closed metadata policy')))
        self.actual_source=gate._current_source
        self.source_reader=self.stack.enter_context(patch.object(gate,'_current_source',side_effect=lambda *a,**kw:deepcopy(self.source)))
        self.plan_reader=self.stack.enter_context(patch.object(gate,'candidate_plan',side_effect=lambda *a,**kw:deepcopy(self.expected)))
        self.stack.enter_context(patch.object(gate,'android',return_value=self.owner))
        self.stack.enter_context(patch.object(self.owner,'plan',side_effect=lambda *a,**kw:deepcopy(self.owner_plan)))

    def object(self,endpoint):
        if endpoint=='actions/workflows/repository-checks.yml':return self.registration
        if endpoint=='actions/runs/100':return self.run
        if endpoint=='actions/runs/100/attempts/1':return self.attempt
        if endpoint.startswith('check-runs/'):return self.checks[int(endpoint.rsplit('/',1)[-1])]
        raise AssertionError('unexpected native GET '+endpoint)

    def verify(self):
        return gate.verify_current_owner(Path('/candidate'),self.event,self.sha,self.needs,self.environment,
            self.adapter,clock=lambda:self.now)

    def test_current_completed40_owner_does_not_relabel_outer_pending_or_use_commonE(self):
        before=deepcopy(self.run)
        value=self.verify()
        self.assertEqual(value['kind'],'current-original-android-owner')
        self.assertTrue(value['verified']);self.assertFalse(value['qualification']);self.assertTrue(value['executed'])
        self.assertEqual(self.run,before);self.assertEqual(self.run['status'],'in_progress')
        self.assertNotIn('environment',value);self.assertNotIn('receipt',value)
        self.assertEqual(self.source_reader.call_count,2)

    def test_default_capability_cannot_be_claimed_by_legacy_flags_or_outputs(self):
        with patch.object(gate,'SOURCE_CAPABILITY',False),patch.object(gate,'ACTIVATION_READY',True),self.assertRaises(ValueError):self.verify()
        self.source_reader.assert_not_called()

    def test_missing39_failed_skipped_runtime_and_verify_steps_remain_red(self):
        for change in ('39','missing','failed','skipped','runtime','verify','missing-step','wrong-app','suite','hash-output'):
            jobs,checks,owner,needs=deepcopy(self.jobs),deepcopy(self.checks),deepcopy(self.owner_plan),deepcopy(self.needs)
            if change=='39':self.owner_plan['executions'].pop(next(iter(self.owner_plan['executions'])))
            elif change=='missing':self.jobs.pop(1)
            elif change in ('failed','skipped'):
                self.jobs[1]['conclusion']='failure' if change=='failed' else 'skipped'
                self.checks[301]['conclusion']=self.jobs[1]['conclusion']
            elif change in ('runtime','verify'):
                self.jobs[1 if change=='runtime' else 2]['steps'][0]['conclusion']='failure'
            elif change=='missing-step':self.jobs[1]['steps']=[]
            elif change=='wrong-app':self.checks[301]['app']['id']=123
            elif change=='suite':self.checks[301]['check_suite']['id']=999
            else:self.needs['android']['outputs']['inventory']='sha256:'+'f'*64
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
            self.jobs,self.checks,self.owner_plan,self.needs=jobs,checks,owner,needs

    def test_current_attempt_run_source_and_newest_all_status_authority_are_fixed(self):
        for change in ('attempt','completed','foreign','head','callee','ref','registration','newer-pending','newer-failed','tie'):
            saved=deepcopy((self.run,self.attempt,self.listed,self.registration))
            if change=='attempt':self.run['run_attempt']=2
            elif change=='completed':self.run.update(status='completed',conclusion='success')
            elif change=='foreign':self.run['repository']['id']=123
            elif change=='head':self.run['head_sha']='f'*40
            elif change=='callee':self.attempt['referenced_workflows']=[]
            elif change=='ref':self.attempt['referenced_workflows'][0]['sha']='f'*40
            elif change=='registration':self.registration['id']=987
            else:
                other=deepcopy(self.run);other['id']=101
                if change!='tie':other['run_started_at']='2026-10-16T19:10:00Z'
                if change=='newer-failed':other.update(status='completed',conclusion='failure')
                self.listed.append(other)
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
            self.run,self.attempt,self.listed,self.registration=saved

    def test_duplicate_native_owner_ordering_and_command_window_fail(self):
        for change in ('duplicate','unknown','ordering','step-window','future'):
            saved=deepcopy(self.jobs)
            if change=='duplicate':self.jobs.append(deepcopy(self.jobs[1]))
            elif change=='unknown':self.jobs.append({'name':'android / unknown-owner'})
            elif change=='ordering':self.jobs[2]['started_at']='2026-10-16T19:02:00Z'
            elif change=='step-window':self.jobs[1]['steps'][0]['started_at']='2026-10-16T18:00:00Z'
            else:self.jobs[1]['completed_at']='2026-10-16T21:00:00Z'
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
            self.jobs=saved

    def test_source_plan_and_native_bookends_are_fresh(self):
        original=self.source_reader.side_effect
        for change in ('source','plan','jobs','registration'):
            count=0
            def source(*a,**kw):
                nonlocal count
                count+=1;value=deepcopy(self.source)
                if count==2 and change=='source':value[1]['default']='f'*40
                if count==2 and change=='jobs':self.jobs[1]['steps'][0]['name']='changed step'
                if count==2 and change=='registration':self.registration['state']='disabled_manually'
                return value
            self.source_reader.side_effect=source
            if change=='plan':self.plan_reader.side_effect=[deepcopy(self.expected),{**self.expected,'plan':'sha256:'+'f'*64}]
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
            self.jobs[1]['steps'][0]['name']=gate.CURRENT_JOBS['android / execute']
            self.registration['state']='active'
            self.plan_reader.side_effect=lambda *a,**kw:deepcopy(self.expected)
        self.source_reader.side_effect=original

    def test_independently_unselected_owner_requires_exact_skip_and_no_execution(self):
        self.expected['required']=False;self.needs={'android':{'result':'skipped','outputs':{}}}
        self.jobs=[deepcopy(self.outer)]
        metadata=self.A.METADATA_WORKFLOW
        self.current[metadata]={'mode':'100644','type':'blob','sha':'b'*40}
        refs=[{'path':gate.REPOSITORY+'/'+metadata+'@'+self.sha,'sha':self.sha,'ref':'refs/pull/17/merge'}]
        self.attempt['referenced_workflows']=refs;self.run['referenced_workflows']=deepcopy(refs)
        value=self.verify();self.assertFalse(value['executed'])
        for job in ({'name':'android / execute','status':'completed','conclusion':'success'},
                    {'name':'android / execute','status':'completed','conclusion':'failure'}):
            self.jobs=[deepcopy(self.outer),job]
            with self.assertRaises(ValueError):self.verify()
        self.jobs=[deepcopy(self.outer)];self.needs['android']['outputs']={'verified':'true'}
        with self.assertRaises(ValueError):self.verify()

    def test_unselected_owner_still_requires_actual_outer_App_source_and_attempt(self):
        self.expected['required']=False;self.needs={'android':{'result':'skipped','outputs':{}}}
        self.jobs=[deepcopy(self.outer)]
        for change in ('missing','app','suite','attempt','check','source'):
            saved=deepcopy((self.jobs,self.checks,self.run,self.attempt,self.listed))
            if change=='missing':self.jobs=[]
            elif change=='app':self.checks[399]['app']['id']=123
            elif change=='suite':self.checks[399]['check_suite']['id']=987
            elif change=='attempt':self.jobs[0]['run_attempt']=2
            elif change=='check':self.checks[399]['status']='completed'
            else:
                self.run['referenced_workflows']=[];self.attempt['referenced_workflows']=[]
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
            self.jobs,self.checks,self.run,self.attempt,self.listed=saved

    def test_actual_source_helper_checks_API_B_M_D_and_all_four_native_targets(self):
        execution,inputs,A,S=gate._native_modules()
        packages=gate.packages()
        manifest=json.loads((ROOT/'.github/package-workflow-generations.json').read_bytes())['generations']
        old=next(row for row in manifest if row['name']=='android-owned-npm5-sync-ci-v1')
        bootstrap=next(row for row in manifest if row['name']=='npm-consumers-sync-ci-v1')
        future=deepcopy(manifest[-1]);future['name']=gate.CURRENT_SOURCE_GENERATION
        future['workflows']['.github/workflows/repository-checks.yml']={'mode':'100644','type':'blob','sha':'e'*40}
        before=deepcopy(old['workflows']);current=deepcopy(future['workflows'])
        current[gate.WORKFLOW]=gate._blob((ROOT/(gate.OWNED+'/android-required.yml')).read_bytes())
        default={'trusted-D.py':{'mode':'100644','type':'blob','sha':'f'*40}}
        maps={self.base:before,self.sha:current,self.default:default}
        trees={revision:str(index+6)*40 for index,revision in enumerate(maps)}
        live_labels=[]
        def get(endpoint):
            if endpoint.startswith('pulls/'):
                return {**deepcopy(self.event['pull_request']),'number':17,'state':'open','labels':deepcopy(live_labels)}
            if endpoint.startswith('branches/'):
                name=endpoint.split('/')[-1]
                return {'name':name,'protected':True,'commit':{'sha':self.default if name=='main' else self.base}}
            if endpoint.startswith('git/commits/'):
                revision=endpoint.split('/')[-1];return {'sha':revision,'tree':{'sha':trees[revision]}}
            raise AssertionError(endpoint)
        def tree(oid):
            revision=next(revision for revision,item in trees.items() if item==oid)
            return {'sha':oid,'truncated':False,'tree':[{'path':path,**item} for path,item in maps[revision].items()]}
        refs={'default':self.default,'default_ref':'main'}
        adapter=SimpleNamespace(current=lambda _: (deepcopy(self.binding),deepcopy(refs)),
            _object=get,api=SimpleNamespace(immutable_tree=tree))
        env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':gate.REPOSITORY,'GITHUB_REPOSITORY_ID':str(gate.REPOSITORY_ID),
            'GITHUB_EVENT_NAME':'pull_request','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'repository-checks',
            'RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24','GITHUB_REF':'refs/pull/17/merge',
            'GITHUB_RUN_ID':'100','GITHUB_SHA':self.sha,'GITHUB_WORKFLOW_SHA':self.sha,
            'GITHUB_WORKFLOW_REF':gate.REPOSITORY+'/.github/workflows/repository-checks.yml@refs/pull/17/merge',
            'GITHUB_BASE_REF':'android-phone','GITHUB_HEAD_REF':self.binding['head_ref']}
        # Existing strict controller and handoff validators have their own real
        # source tests. These spies isolate this new caller's actual API/local
        # source binding and require D alone to supply executable authority.
        with patch.object(gate,'packages',return_value=packages), \
             patch.object(packages,'workflow_generations',return_value=[bootstrap,old,future]), \
             patch.object(execution,'checkout_identity',return_value=(self.default,trees[self.default])), \
             patch.object(inputs,'full_tree',return_value=default), \
             patch.object(gate,'_sources',side_effect=lambda candidate,commit=None:SimpleNamespace(entries=before if commit else current)), \
             patch.object(S,'compatibility',return_value={'trusted':'actual D'}) as compatibility, \
             patch.object(S,'actual_import_inventory',return_value={}), \
             patch.object(gate,'validate_owned_generation') as handoff:
            def source():return self.actual_source('/candidate',self.event,self.sha,env,adapter,ROOT)
            for prior in (bootstrap,old):
                before.clear();before.update(deepcopy(prior['workflows']))
                for target in gate.CURRENT_SOURCE_TARGETS:
                    with self.subTest(predecessor=prior['name'],target=target):
                        self.binding['base_ref']=target;self.event['pull_request']['base']['ref']=target;env['GITHUB_BASE_REF']=target
                        self.assertEqual(source()[2:4],(current,default))
                        self.assertEqual(compatibility.call_args.args,(default,default,'main'))
                        self.assertEqual(handoff.call_args.kwargs['before_sha'],self.base)
            # A bootstrap is a complete independently authenticated tuple.
            # Its individual known files/modes cannot be mixed or projected.
            before.clear();before.update(deepcopy(bootstrap['workflows']))
            for change in ('mixed','mode','missing'):
                path='.github/workflows/project-tests.yml';saved=deepcopy(before)
                if change=='mixed':before[path]=deepcopy(old['workflows'][path])
                elif change=='mode':before[path]['mode']='100755'
                else:before.pop(path)
                with self.subTest(bootstrap=change),self.assertRaises(ValueError):source()
                before.clear();before.update(saved)
            # The existing immutable handoff still has authority over the six
            # actual legacy source owners, including on a row13 predecessor.
            with patch.object(gate,'validate_owned_generation',side_effect=ValueError('legacy owner missing')),self.assertRaises(ValueError):source()
            before.clear();before.update(deepcopy(old['workflows']))
            live_labels.append({'name':'unrelated-label'})
            self.assertEqual(source()[2:4],(current,default))
            for labels in ([{'name':'android-long-diagnostics'}],[{'name':'duplicate'},{'name':'duplicate'}],['invalid']):
                live_labels[:]=labels
                with self.assertRaises(ValueError):source()
            live_labels[:]=[]
            self.event['pull_request']['labels']=[{'name':'android-long-diagnostics'}]
            with self.assertRaises(ValueError):source()
            self.event['pull_request']['labels']=[]
            for change in ('job','target','default','root','B','M','branch','mode','mixed'):
                with self.subTest(change=change):
                    if change=='job':
                        with patch.dict(env,{'GITHUB_JOB':'android'}),self.assertRaises(ValueError):source()
                    elif change=='target':
                        original=self.binding['base_ref'];self.binding['base_ref']='unknown'
                        with self.assertRaises(ValueError):source()
                        self.binding['base_ref']=original
                    elif change=='default':
                        refs['default_ref']='other'
                        with self.assertRaises(ValueError):source()
                        refs['default_ref']='main'
                    elif change=='root':
                        with patch.object(execution,'checkout_identity',return_value=('a'*40,trees[self.default])),self.assertRaises(ValueError):source()
                    elif change in ('B','M'):
                        side=self.base if change=='B' else self.sha
                        saved=maps[side];maps[side]={'unknown':{'mode':'100644','type':'blob','sha':'f'*40}}
                        with self.assertRaises(ValueError):source()
                        maps[side]=saved
                    elif change=='branch':
                        with patch.object(adapter,'_object',side_effect=lambda endpoint:{'name':endpoint.split('/')[-1],'protected':False}),self.assertRaises(ValueError):source()
                    else:
                        saved=deepcopy(current)
                        if change=='mode':current[gate.WORKFLOW]['mode']='120000'
                        else:current['.github/workflows/repository-checks.yml']['sha']='f'*40
                        with self.assertRaises(ValueError):source()
                        current.clear();current.update(saved)

    def test_only_typed_metadata_nonproducer_may_be_newer_than_current40(self):
        other=deepcopy(self.run);other.update(id=101,status='queued',conclusion=None,run_started_at=None)
        self.listed.append(other)
        record={'kind':'trusted native metadata nonproducer','run_id':101,'source':self.sha}
        self.metadata.return_value=record
        self.assertTrue(self.verify()['verified'])
        self.assertEqual(self.metadata.call_count,4)
        self.assertEqual(self.metadata.call_args.args[0],other)
        for result in (None, ValueError('unknown successful source')):
            self.metadata.reset_mock()
            if result is None:self.metadata.return_value=None
            else:self.metadata.side_effect=result
            with self.subTest(result=type(result).__name__),self.assertRaises(ValueError):self.verify()
        self.metadata.side_effect=[record,{**record,'source':'f'*40}]
        with self.assertRaises(ValueError):self.verify()

    def test_only_shared_native_intent_projection_may_ignore_metadata_progress(self):
        other=deepcopy(self.run);other.update(id=101,status='queued',conclusion=None,run_started_at=None)
        self.listed.append(other)
        record={'kind':'authenticated-metadata-nonproducer-intent','run':{'id':101},
            'source':{'complete':'authenticated native source'},'candidate':{'merge_sha':self.sha}}
        self.metadata.return_value=record
        calls=0
        def source(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:self.listed[1].update(status='in_progress',updated_at='2026-10-16T19:59:00Z')
            return deepcopy(self.source)
        self.source_reader.side_effect=source
        self.assertTrue(self.verify()['verified'])
        self.assertEqual(self.metadata.call_count,4)
        self.assertEqual([call.args[1] for call in self.inventory.call_args_list if call.args[0]['id']==101],[record,record])
        # Historical completed-marker records keep the raw inventory bookend.
        self.metadata.return_value={**record,'kind':'historical completed marker'}
        calls=0;self.listed[1]['status']='queued'
        with self.assertRaises(ValueError):self.verify()

    def test_future_run_or_mixed_attempt_source_cannot_enter_current_owner(self):
        for field in ('repository','head_repository','pull_requests','referenced_workflows','run_started_at'):
            saved=deepcopy(self.attempt)
            if field=='run_started_at':self.run[field]='2026-10-16T21:00:00Z';self.attempt[field]=self.run[field];self.listed[0][field]=self.run[field]
            elif field=='repository':self.attempt[field]={'full_name':'foreign/repo','id':123}
            elif field=='head_repository':self.attempt[field]={'full_name':'foreign/repo','id':123}
            else:self.attempt[field]=[]
            with self.subTest(field=field),self.assertRaises(ValueError):self.verify()
            self.attempt=saved

    def test_repository_graph_is_not_imported_before_default_authentication(self):
        with patch.object(gate,'_protected_default',side_effect=ValueError('untrusted actualD')), \
             patch.object(gate,'_native_modules',side_effect=AssertionError('no repository import')) as imports:
            with self.assertRaises(ValueError):self.verify()
        imports.assert_not_called()

    def test_dispatch_preserves_legacy_admission_even_with_current_source_capability(self):
        for generation in ('npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1'):
            with self.subTest(generation=generation), \
                 patch.object(gate,'SOURCE_CAPABILITY',True), \
                 patch.object(gate,'_source_generation',return_value=generation), \
                 patch.object(gate,'verify_current_owner',side_effect=AssertionError('no unrequested40')):
                self.assertIsNone(gate.current_source_owner('/candidate',self.event,self.sha,self.needs,self.environment))
        with patch.object(gate,'_source_generation',return_value=gate.CURRENT_SOURCE_GENERATION), \
             patch.object(gate,'verify_current_owner',return_value={'verified':True}) as current:
            self.assertEqual(gate.current_source_owner('/candidate',self.event,self.sha,self.needs,self.environment),{'verified':True})
        current.assert_called_once()


class AndroidDefaultBootstrapTests(unittest.TestCase):
    def setUp(self):
        _,_,_,source=gate._native_modules()
        self.temp=tempfile.TemporaryDirectory(prefix='android-default-bootstrap-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in sorted(set(source.CONTROLLERS)|set(source.IMPORT_MEMBERS)):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
            path.chmod(0o755 if name=='tests/run-project-tests.py' else 0o644)
        for command in (('init','--quiet'),('add','--all'),('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                'commit','--quiet','-m','Immutable actual default source')):gate._bootstrap_git(self.root,*command)
        self.commit=gate._bootstrap_git(self.root,'rev-parse','HEAD').decode().strip()
        self.tree=gate._bootstrap_git(self.root,'rev-parse','HEAD^{tree}').decode().strip()
        self.entries=[]
        for row in gate._bootstrap_git(self.root,'ls-tree','-rz','--full-tree','HEAD').split(b'\0'):
            if row:
                header,path=row.split(b'\t');mode,kind,sha=header.decode().split()
                self.entries.append({'path':path.decode(),'mode':mode,'type':kind,'sha':sha})
        self.ref={'ref':'refs/heads/main','object':{'type':'commit','sha':self.commit}}
        self.branch={'name':'main','protected':True,'commit':{'sha':self.commit}}
        self.api=SimpleNamespace(get=self.get)

    def get(self,endpoint):
        if endpoint=='':return {'full_name':gate.REPOSITORY,'id':gate.REPOSITORY_ID,'default_branch':'main'}
        if endpoint=='git/ref/heads/main':return deepcopy(self.ref)
        if endpoint=='branches/main':return deepcopy(self.branch)
        if endpoint=='git/commits/'+self.commit:return {'sha':self.commit,'tree':{'sha':self.tree}}
        if endpoint=='git/trees/'+self.tree+'?recursive=1':return {'sha':self.tree,'truncated':False,'tree':deepcopy(self.entries)}
        raise AssertionError(endpoint)

    def test_pinned_stdlib_guard_authenticates_real_complete_D_before_exposing_graph(self):
        context=gate._protected_default(self.root,api=self.api)
        self.assertEqual(context['default'],self.commit)
        self.assertEqual(context['admission']['target'],'main')
        self.assertFalse((self.root/'tools/test-evidence/__pycache__').exists())
        self.assertNotIn('trusted_android_default_bootstrap',__import__('sys').modules)

    def test_alias_mode_changed_guard_and_untracked_import_never_execute(self):
        path=self.root/'tools/test-evidence/source_admission.py';raw=path.read_bytes()
        alias=self.root/'guard-copy'
        for change in ('guard','alias','mode','shadow','protection','default'):
            if change=='guard':path.write_bytes(raw+b'\nraise AssertionError("must never execute")\n')
            elif change=='alias':
                alias.write_bytes(raw);path.unlink();path.symlink_to(alias)
            elif change=='mode':path.chmod(0o755)
            elif change=='shadow':
                (self.root/'tools/test-evidence/unknown.py').write_text('raise AssertionError("must never import")\n')
            elif change=='protection':self.branch['protected']=False
            else:self.ref['object']['sha']='a'*40
            with self.subTest(change=change),self.assertRaises(ValueError):gate._protected_default(self.root,api=self.api)
            if path.is_symlink():path.unlink()
            path.write_bytes(raw);path.chmod(0o644)
            alias.unlink(missing_ok=True)
            (self.root/'tools/test-evidence/unknown.py').unlink(missing_ok=True)
            self.branch['protected']=True;self.ref['object']['sha']=self.commit


class AndroidCurrentDispatchTests(unittest.TestCase):
    """Actual immutable Git catalog dispatch; no repository graph import."""
    def test_outer_cli_authenticates_current_Android_before_other_router_imports(self):
        with tempfile.TemporaryDirectory(prefix='android-current-cli-') as directory:
            event=Path(directory)/'event.json'
            event.write_text(json.dumps({'pull_request':{'base':{'ref':'android-phone'}}}))
            with patch.object(checks,'configuration',return_value=({},{})), \
                 patch.object(checks,'bound_project_owners',return_value=({'android':{}},{})), \
                 patch.object(checks,'android_policy',return_value=SimpleNamespace(
                     current_source_owner=lambda *args:(_ for _ in ()).throw(ValueError('untrusted actualD')))), \
                 patch.object(checks,'package_policy',side_effect=AssertionError('router imported before D')) as packages, \
                 patch.object(checks,'browser_policy',side_effect=AssertionError('router imported before D')) as browser, \
                 patch.object(__import__('sys'),'argv',['check.py','verify','--needs-json','{}','--candidate',directory,
                     '--sha','3'*40,'--event',str(event)]),redirect_stderr(io.StringIO()) as output:
                self.assertEqual(checks.main(),1)
            self.assertIn('untrusted actualD',output.getvalue())
            packages.assert_not_called();browser.assert_not_called()

    def test_fresh_isolated_metadata_policy_import_uses_only_fixed_controller_directory(self):
        script='''import importlib.util,sys
from pathlib import Path
root=Path(sys.argv[1]);directory=str(root/'tools/test-evidence')
spec=importlib.util.spec_from_file_location('android_policy',root/'tools/repository-checks/android_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
assert directory not in sys.path and 'producer_workflow' not in sys.modules
policy=gate._current_metadata_policy(99)
assert policy.caller_workflow_id==99 and policy.caller_path=='.github/workflows/repository-checks.yml'
assert directory not in sys.path
# This source-only checkout need not enroll the future metadata pair yet.
assert (policy.generations is None)==(policy.sources is None)
assert policy.generations is None or isinstance(policy.generations,dict) and isinstance(policy.sources,dict)
assert Path(sys.modules['producer_workflow'].__file__).resolve()==root/'tools/test-evidence/producer_workflow.py'
'''
        result=subprocess.run([__import__('sys').executable,'-I','-S','-B','-c',script,str(ROOT)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_complete_legacy_and_future_recipes_dispatch_but_mixed_modes_and_catalogs_do_not(self):
        with tempfile.TemporaryDirectory(prefix='android-current-dispatch-') as directory:
            root=Path(directory)
            gate._bootstrap_git(root,'init','--quiet')
            names=('project-tests','parent-qualification','sync-validation','repository-checks','browser-client','pr-metadata-context')
            paths=['.github/workflows/'+name+'.yml' for name in names]
            old={path:gate._blob(('old '+path+'\n').encode()) for path in paths[:5]}
            future={path:gate._blob(('new '+path+'\n').encode()) for path in paths}
            catalog={'schema':1,'repository':{'full_name':gate.REPOSITORY,'id':gate.REPOSITORY_ID},
                'generations':[{'name':'android-owned-npm5-sync-ci-v1','workflows':old},
                    {'name':gate.CURRENT_SOURCE_GENERATION,'workflows':future}]}
            catalog_path=root/'.github/package-workflow-generations.json'
            def write_workflows(prefix,selected):
                for path in paths:
                    target=root/path
                    if target.is_symlink() or target.exists():target.unlink()
                    if path in selected:
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(prefix+' '+path+'\n');target.chmod(0o644)
            def commit():
                gate._bootstrap_git(root,'add','--all')
                gate._bootstrap_git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                    'commit','--quiet','--allow-empty','-m','Immutable dispatch fixture')
                return gate._bootstrap_git(root,'rev-parse','HEAD').decode().strip()
            write_workflows('old',old);catalog_path.write_text(json.dumps(catalog));before=commit()
            write_workflows('new',future);current=commit()
            with patch.object(gate,'_native_modules',side_effect=AssertionError('dispatch must be stdlib-only')):
                self.assertEqual(gate._source_generation(root,before,root),'android-owned-npm5-sync-ci-v1')
                self.assertEqual(gate._source_generation(root,current,root),gate.CURRENT_SOURCE_GENERATION)
                for change in ('missing','mixed','mode','alias'):
                    write_workflows('new',future);path=root/paths[0]
                    if change=='missing':path.unlink()
                    elif change=='mixed':path.write_text('old '+paths[0]+'\n')
                    elif change=='mode':path.chmod(0o755)
                    else:path.unlink();path.symlink_to(root/paths[1])
                    revision=commit()
                    with self.subTest(change=change),self.assertRaises(ValueError):gate._source_generation(root,revision,root)
                write_workflows('new',future)
                for change in ('unknown','duplicate','nonfinite','incomplete'):
                    value=deepcopy(catalog)
                    if change=='unknown':value['extra']=True
                    elif change=='incomplete':value['generations'][1]['workflows'].pop(paths[-1])
                    raw=json.dumps(value)
                    if change=='duplicate':raw=raw.replace('"schema": 1','"schema": 1, "schema": 1')
                    elif change=='nonfinite':raw=raw.replace('"schema": 1','"schema": NaN')
                    catalog_path.write_text(raw);commit()
                    with self.subTest(change=change),self.assertRaises(ValueError):gate._source_generation(root,current,root)


if __name__ == "__main__":
    unittest.main()
