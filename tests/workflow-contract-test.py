#!/usr/bin/env python3
"""Security and reproducibility contracts for shared repository workflows."""

import fnmatch
import ast
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import tempfile
import unittest
import zlib
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/project-tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/pico4-build.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/pico4-release-candidate.yml"
RELEASE_BUNDLE_WORKFLOW = ROOT / ".github/workflows/release-bundle-attest-draft.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/pico4-device-acceptance.yml"
ANDROID_TESTS_WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
DOCUMENTATION_WORKFLOW = ROOT / ".github/workflows/documentation-checks.yml"
BRANCH_POLICY_WORKFLOW = ROOT / ".github/workflows/branch-policy.yml"
BRANCH_SYNC_WORKFLOW = ROOT / ".github/workflows/branch-sync.yml"
PARENT_QUALIFICATION_WORKFLOW = ROOT / ".github/workflows/parent-qualification.yml"
SYNC_REUSE_WORKFLOW = ROOT / ".github/workflows/sync-test-reuse.yml"
SYNC_VALIDATION_WORKFLOW = ROOT / ".github/workflows/sync-validation.yml"
WORKFLOW_DIRECTORY = ROOT / ".github/workflows"
CODEQL_WORKFLOW = ROOT / ".github/workflows/codeql.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-bootstrap.yml"
MACOS_WORKFLOW = ROOT / ".github/workflows/macos-bootstrap.yml"
RULESETS = ROOT / ".github/rulesets"
RULESET_FILES = {
    "Android target branch topology": "android-target-branches.json",
    "Apple target branch topology": "apple-target-branches.json",
    "Immutable Android, canonical, and archive tags": "android-release-tags.json",
    "Immutable Pico 4 release and dependency tags": "pico4-release-tags.json",
    "Permanent branch governance": "permanent-branches.json",
}
STAGED_RULESET_FILES = {
    "Selected CodeQL security results on main": ROOT / "tools/repository-checks/workflows/codeql-main.json",
}
ACTION_USE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
PROTECTED_GENERATIONS = (
    'protected-shared-producer-v1', 'protected-producer-postmerge-original-e-v1',
    'protected-producer-ci37-v1', 'protected-producer-metadata-ci-v1',
    'protected-producer-seven-target-ci-v1', 'protected-producer-original-default-v1',
)
METADATA_PRODUCER_GENERATIONS = PROTECTED_GENERATIONS[-3:]
SELECTED_SYNC_GENERATIONS = (
    'npm-consumers-sync-ci-v1', 'npm-consumers-sync-ci-budget-v1', 'npm-consumers-metadata-edits-v1',
    'android-owned-npm5-sync-ci-v1', *PROTECTED_GENERATIONS,
)

# Exact historical metadata recipe; available even in a shallow source checkout.
_HISTORICAL_METADATA_CODEQL = 'c-rk*ZBrXL68`RAp?Fgnn`OoZOd!sZT5oVA+_8p@P3m%4$|cXpSYa$pBn{xa{P%5*G-HiDPO`}s_vJ`cu%%Y3U!QI@KcQnT=9nooCkjVcVI<QqBvNwm6eWU4B5nvGcQ{lip^T9TVTR+y2O{7@gd|TzNDz+ZR7%QOP-A#by68EN$RDS*8fV=aLP;uT`Zq!ofmt{svWwo%F=g8bCrM0v_cP^kTk{s2M)`*QmdrRK%da=W{p=?+<d@kk305=d(<{aWG4~?mqx#lXYb%&X^-Q8T9t-k5B~lp*wMa6tctSwSZ6rwkNiINS!5RGkcaw-J5?$V#G7>I`(%7ouqYwn?qWaDO+Cy9LuT!tp5+bbmr6vnGQ-moHOAs8@YVbWwg&-_k=<T0S4=Hk|GF8w#l?pL(1O5y_8xkW!tI+!t$8<_Vtbj4%0=OkH24_<x;j>I*6#%;{!PBG*mqz4$>_7bY5nWL=ODDlC7uVC6-=fc--DS9nslc^=z|#2y?*H^Drx9dYc?zOX%W`ytJmUusJ$i&5lxV^kW>-W86D*0|ZB*_ms$$~YxN??9i>5xD%agJ(jWoGevWf>%YJ+En^C|Na!LPtHV0tA|Qmeh=lguS~cKIe>j5AH9^inm0yER9G&R;EElhM#=w<O|NAIc2iTF`T3)q0P$0X311I4@(AN*$*`D==iO+&i+B2)__73!OU^Eaq`d2Oo(^X!C;+5&?%5O$s4#e2W*dky)*g(FQA|fr*(+E(<cAHtE-iuW6EiubU>f%fYUHRs!BEnpi2XX`A`hX5}48And7H_?ea6J>#WeW(kC+Q}_iSXz&fi5HBf)kjY3POr)>VGo7SNrT%UwXm<>_&^h6$^5>MLN;_gdTZW}1RfQh84aS_si!RdPFBM6ojZRA)l*mj3>YqXu_atO2D-ISE%R>@kcO$*t%t^EDC6-#0pONrdYoWtks=PQzDpA5?8ZIn-9)8v*tx%tXW54c2dtqmn>|-46Pw-)T|8RFd!UvB#JMD1iaA)^mZ-Sq+Cp!RIHwQsG*eMv^LKt_8Z(w^eHF}g18X${Hs<>DL5t(9$sIdX<r3LbO(am*m*NFgKlphKb=^Vu|C^3cqi9;k4EF|%Box13gvk9)}JeIAcAcjy@&_G})h(8KfL1L|#`V|TJl`cUj^LohVP+kBr43GgjYs@l`ZbG=YfJR-jRICto<C^Zp%kk*!-~B<!eu`fcR<_chH#&LUAOGGT^^SX^-uPrN>JLWdRCN-sMJ&w{)nyAg(?!pG*XRocm2oe3M{9!tO%MgiVhKrQEx~qX1=SzEI2paX_-)*O4FZqPd!v{2eACYWb%kQk`@OFzjQq>pvy0LB#i+jS8yq1(aoZ<B)<iVYa88-N0%Tq~1ETcnIsE`oPZtpH{_@A9Kq0!bGbJjV`4LGp!R`-dhb=&>Hnad+#C3tRIcQmEA@YZ9sS`ru+@^f^tvBqChc9~-cv5OxbfpdC46n5j6EcOy(^=L;rBr&}8yufN60P5}M!Jm1b$LuTu$oOS{z#&bPf`xedjbGR<L^ndthLjb_GbyTd|z<xhP&@;llWSN`or9cI*$qxyH`@bzQ#7sS~nS=<sD{Lq25W(Dm3xYFTZ%_Z#-v<&J!*a(g(H?cVTxb_&f{ym`-xCbNK4=g}cyEb~uPRj$}g<G`v+&yk?;Lg|Y6P8qKD|VOesIGH!3ZV#T|3=&*#Bma-(e=bvNmQg=T)*)xku%B0e5W}`U2jbg~Y<~kGS&Li~p2FEEu5Rk}xq6{^>clZX&P|!sA*}EtE=xsw+nOV|nLUJwX3x=-58bFYKA~iT9AiJUPFnQ~hfYQ4Jju@C>X<MCc$<uiQ6x>4VMH)-f9C_$xWA!MVCvvHC6V|;ynb-UxAKkZPETj^R2}HHSpb3t=C8ANqDG^Yg8qU4i9q|5x$QWOfg*+Moj+ESc{zl`NeG$7|{jw&S9=fvmg;u#lQw?B8Ie=+;&o-Wo;=P_S^J<BjSvNh^?|IcI=svbTH^H&6Cg@$!0XB2cuwA_oplIg5L8=F?RF(8u_jpu7-@nly@3sF{x4+iEXQ5y_R{_X#waCwF6!fPU-u<OwWh}G|(A-qUml`boH9Q+MDphsj^V`~GJ2ufdq`x{9^d2kz=JLHF_X(qVTQ{F}uH%+c%BWhA+P*O@Od1_pn(o&ynsyEkr~6O#qr-Oen6wW_doSudKIlxzB-+Q5&i)iX**nzYcY?ix;K@e$vvSo%Go`@Nt(L8e&_J{*uNUAls7|sK@mr?BJl}^<j9^l8vm5Ll1iLG%F~sBD<4&Nk2tG(vh3qCkRuZgS!zU??Vf+J}A-7=a<7`1RPwACEr7+@gp65o2To^-?zsk$4=lhgGuOZ;wKyH^0Qz%3N6xXP)-OM*OJI~LK`+uB{U-w@PPtFGJQ&9V>h;S>2W%k`IhkoMd`d_-V4z<x3e^tAl0oHGcE{nncWPs_3%oX%OFm7uVXi)9z>`9P2E9;u>r5M;73-B|1<>u<J>4cYibi*j8Ecb)T3C_2bi>6z4-kLMpc?G@vzA?&ukAy10J<mivN?q83>I_6S<=?P>+J8P8zv>S!PDh(Vr35EK=$|V{tHw6wr#I-GzWHyz;udT8ifg_nuS?44w6;-FN-C+J+nEXv%W~DBl$6IJ5HMZK;!{?cx^@=WL{FcVNVl4Zgfou3VQzQ}gvCG#9w30d%7~;V$Il+^J_VeFfyqvp8<9AyeRa~6d)TJX{|8?G_`qw!P(?pwD1&(fVOmD}rwHp0x6<9a3)bH5|LdVjj!F5Sbc&cQN>>hY){62+XN0!0_y2PaK+r!PpY{eXE_yHe!!O`f#aQ}>=7L#?8(W27Y*G8-$ihqkb^ld4C#?MizY_pz'

def historical_metadata_codeql():
    raw = zlib.decompress(base64.b85decode(_HISTORICAL_METADATA_CODEQL))
    if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != '3a273057a38255ca368d3028594fb94227ba7c3b':
        raise AssertionError('historical metadata CodeQL recipe changed')
    return raw.decode()


def has_automatic_app_trigger(source):
    return re.search(r"(?m)^  (?:push|pull_request):", source) is not None


def workflow_data(source):
    import yaml
    try:
        return yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise ValueError('invalid workflow YAML') from error


def workflow_events(source):
    data = workflow_data(source)
    return data.get('on', data.get(True))


def codeql_generation(case, source):
    """Admit exact old/new result workflows, never arbitrary metadata guards."""
    spec = importlib.util.spec_from_file_location('workflow_contract_codeql', ROOT / 'tools/repository-checks/codeql.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    def blob(value):
        raw = value.encode()
        return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    previous = ROOT / 'tools/repository-checks/workflows/codeql-results.yml'
    successor = ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml'
    pinned = successor.with_name('codeql-pinned.yml')
    metadata = successor.with_name('codeql-metadata.yml')
    case.assertEqual(blob(previous.read_text()), policy._RESULTS_WORKFLOW)
    case.assertEqual(blob(successor.read_text()), policy._RETARGET_RESULTS_WORKFLOW)
    case.assertEqual(blob(pinned.read_text()), policy._PINNED_RESULTS_WORKFLOW)
    case.assertEqual(blob(historical_metadata_codeql()), policy._METADATA_RESULTS_WORKFLOW)
    case.assertEqual(blob(metadata.read_text()), policy._SCHEDULING_RESULTS_WORKFLOW)
    helper = metadata.with_name('pr-metadata-context.yml')
    case.assertEqual(blob(helper.read_text()), policy._SCHEDULING_SOURCE_WORKFLOW)
    case.assertIn((blob(metadata.read_text()), blob(helper.read_text())), policy.result_workflow_sources())
    known = {policy._SELECTIVE_WORKFLOW: 'selective', policy._RESULTS_WORKFLOW: 'results',
             policy._RETARGET_RESULTS_WORKFLOW: 'retarget-results',
             policy._PINNED_RESULTS_WORKFLOW: 'pinned-results',
             policy._METADATA_RESULTS_WORKFLOW: 'metadata-pinned-results',
             policy._SCHEDULING_RESULTS_WORKFLOW: 'scheduling-pinned-results'}
    identity = blob(source)
    case.assertIn(identity, known, 'unreviewed CodeQL workflow cannot inherit omission contracts')
    return known[identity]


def codeql_analyze_condition(case, source):
    generation = codeql_generation(case, source)
    condition = ("needs.select.outputs.metadata_only != 'true' && needs.select.outputs.scan == 'true'"
                 if generation in {'retarget-results', 'pinned-results', 'metadata-pinned-results', 'scheduling-pinned-results'}
                 else "needs.select.outputs.scan == 'true'")
    if generation == 'scheduling-pinned-results':
        intent = "github.event_name == 'pull_request' && ((github.event.action == 'edited' && !github.event.changes.base && (github.event.changes.title || github.event.changes.body)) || ((github.event.action == 'labeled' || github.event.action == 'unlabeled') && github.event.label.name != 'android-long-diagnostics'))"
        condition = "always() && !cancelled() && needs.select.result == 'success' && " + condition + ' && !(' + intent + ')'
    return condition


def reviewed_package_generation():
    """Bind the complete current tuple, including the Android successor callee."""
    spec = importlib.util.spec_from_file_location(
        'workflow_contract_packages', ROOT / 'tools/repository-checks/package_checks.py')
    packages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packages)
    name = packages.validate_wiring(ROOT)
    if name in ('android-owned-npm5-sync-ci-v1', *METADATA_PRODUCER_GENERATIONS):
        spec = importlib.util.spec_from_file_location(
            'workflow_contract_android', ROOT / 'tools/repository-checks/android_gate.py')
        android = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(android)
        tree = {}
        paths = packages.METADATA_WORKFLOW_PATHS if name in METADATA_PRODUCER_GENERATIONS else packages.CONSUMER_WORKFLOW_PATHS
        for relative in (*paths, '.github/workflows/android-required.yml'):
            path = ROOT / relative
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o111:
                raise AssertionError('owned Android workflow must be an ordinary source')
            tree[relative] = android._blob(path.read_bytes())
        if android.validate_tree_wiring(tree) != name:
            raise AssertionError('owned Android requires its exact complete generation')
    return name


def prospective_package_tree():
    """Read the exact six future22 endpoints, independently of active source13."""
    spec = importlib.util.spec_from_file_location(
        'prospective_workflow_packages', ROOT / 'tools/repository-checks/package_checks.py')
    packages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packages)
    sources = {
        '.github/workflows/project-tests.yml': 'producers/protected-project-tests-android-platform.yml',
        '.github/workflows/parent-qualification.yml': 'producers/parent-qualification-android-platform.yml',
        '.github/workflows/repository-checks.yml': 'producers/repository-checks.yml',
        '.github/workflows/sync-validation.yml': 'sync-ci-selection.yml',
        '.github/workflows/browser-client.yml': 'npm-consumers/browser-client.yml',
        '.github/workflows/pr-metadata-context.yml': 'metadata-edits/pr-metadata-context.yml',
    }
    tree = {}
    for target, relative in sources.items():
        path = ROOT / 'tools/repository-checks/workflows' / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 not in {0o444, 0o644}:
            raise AssertionError('future recipe must be an ordinary non-executable source')
        raw = path.read_bytes()
        tree[target] = {'mode': '100644', 'type': 'blob',
            'sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}
    if packages.validate_tree_wiring(tree) != 'protected-producer-original-default-v1':
        raise AssertionError('future sources require the complete exact22 generation')
    return packages, tree


def selected_sync_recipe():
    """Keep deployed13/14/20/21 selected-sync recipes distinct from future22."""
    spec = importlib.util.spec_from_file_location(
        'selected_sync_packages', ROOT / 'tools/repository-checks/package_checks.py')
    packages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packages)
    generation = reviewed_package_generation()
    row = next(row for row in packages.workflow_generations() if row['name'] == generation)
    raw = SYNC_VALIDATION_WORKFLOW.read_bytes()
    entry = {'mode': '100644', 'type': 'blob',
        'sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}
    if SYNC_VALIDATION_WORKFLOW.is_symlink() or SYNC_VALIDATION_WORKFLOW.stat().st_mode & 0o777 not in {0o444, 0o644} \
            or row['workflows']['.github/workflows/sync-validation.yml'] != entry:
        raise AssertionError('synchronization recipe differs from its whole deployed generation')
    return generation in SELECTED_SYNC_GENERATIONS


def sync_condition(legacy, selected, *, setup=False):
    """Admit selected conditions only with an exact complete reviewed caller."""
    if not selected_sync_recipe():
        return legacy
    installed_empty = reviewed_package_generation() == 'protected-producer-original-default-v1'
    if installed_empty:
        # The extra lane belongs to installed22, never to an older caller just
        # because a newer canonical recipe is staged beside it. Both complete
        # endpoint maps must independently match the enrolled catalog row.
        prospective_package_tree()
        canonical = ROOT / 'tools/repository-checks/workflows/sync-ci-selection.yml'
        if SYNC_VALIDATION_WORKFLOW.read_bytes() != canonical.read_bytes():
            raise AssertionError('installed empty synchronization requires the exact canonical recipe')
    if setup:
        steps = workflow_data(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        product = next(step for step in steps if step['name'] == 'Verify exact candidate suites and complete runtime identity')
        if 'SYNC_VALIDATOR_PYTHON' in product.get('env', {}):
            expected = "${{ steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.native_setup != '' && 'python3' || 'build/host-tests-env/bin/python' }}"
            if product['env']['SYNC_VALIDATOR_PYTHON'] != expected or '--expected-native-setup "$EXPECTED_NATIVE_SETUP"' not in product['run']:
                raise AssertionError('unreviewed no-setup interpreter or expected proof transport')
            selected = "(steps.select.outputs.consumer_setup != 'none' || steps.select.outputs.native_setup == '') && " + selected
    if installed_empty:
        if setup:
            selected += " && !(steps.select.outputs.lane == 'verified-empty' && steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.empty_setup != '')"
        elif selected == "steps.select.outputs.lane != 'legacy-bounded'":
            selected += " && steps.select.outputs.lane != 'verified-empty'"
    return selected


def assert_project_caller_routing(case, source):
    """Finite successors bind their whole generation and exact project route."""
    templates = (
        ('tools/repository-checks/workflows/npm-consumers/repository-checks.yml',
         ('npm-consumers-v1', 'npm-consumers-sync-ci-v1'), False),
        ('tools/repository-checks/workflows/metadata-edits/repository-checks.yml',
         ('npm-consumers-metadata-edits-v1',), True),
        ('tools/repository-checks/workflows/android-owned/repository-checks.yml',
         ('android-owned-npm5-sync-ci-v1',), True),
        ('tools/repository-checks/workflows/producers/repository-checks.yml',
         METADATA_PRODUCER_GENERATIONS, True),
    )
    for relative, generations, metadata in templates:
        if source != (ROOT / relative).read_text(encoding='utf-8'):
            continue
        case.assertIn(reviewed_package_generation(), generations)
        condition = ("needs.route.outputs.package_host_mode == 'full' || "
                     "needs.route.outputs.package_host_mode == 'tool-dependencies' || "
                     "needs.route.outputs.package_set != '[]'")
        if metadata:
            condition = "needs.route.outputs.metadata_only != 'true' && (" + condition + ")"
        if reviewed_package_generation() == 'protected-producer-original-default-v1':
            condition = "always() && !cancelled() && needs.route.result == 'success' && " + condition
            intent = "github.event_name == 'pull_request' && ((github.event.action == 'edited' && !github.event.changes.base && (github.event.changes.title || github.event.changes.body)) || ((github.event.action == 'labeled' || github.event.action == 'unlabeled') && github.event.label.name != 'android-long-diagnostics'))"
            condition += " && !(" + intent + ")"
        case.assertEqual(workflow_data(source)['jobs']['project']['if'], condition)
        return 'package_host_mode'
    # An unadmitted caller cannot inherit the successor's formatting-only omission.
    case.assertIn("if: needs.route.outputs.mode == 'full'", source)
    return 'mode'


def push_filters(source):
    """Check the semantic push filters independently of YAML presentation."""
    events = workflow_events(source)
    result = events.get('push') if isinstance(events, dict) else None
    if not isinstance(result, dict) or set(result) != {'branches', 'paths-ignore'}:
        raise ValueError('expected explicit branches and paths-ignore filters')
    for values in result.values():
        if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./*-]+', value)
                for value in values):
            raise ValueError('unsupported push filter patterns')
    if result['paths-ignore'] != ['**/*.md']:
        raise ValueError('routing matrix supports only the existing Markdown exclusion')
    return result


def selects_host_push(source, branch, changed_paths):
    filters = push_filters(source)
    if not any(fnmatch.fnmatchcase(branch, item) for item in filters["branches"]):
        return False
    # GitHub's **/ also matches the repository root, unlike fnmatch's **/.
    return any(not path.endswith(".md") for path in changed_paths)


def artifact_retention_limit(workflow_name, artifact_lines):
    # The existing iOS source checkpoint is a verified reusable build input.
    # Diagnostic artifacts and every other workflow retain the ordinary limit.
    checkpoint_paths = {
        "build-ios/qt-source-checkpoint/checkpoint.tar.gz",
        "build-ios/qt-source-checkpoint/manifest.json",
    }
    source_checkpoint = (workflow_name == "ios-qt-source.yml" and
                         checkpoint_paths <= {line.strip() for line in artifact_lines})
    return 90 if source_checkpoint else 30


class BrowserTriggerContracts(unittest.TestCase):
    """Browser product work is selected only by changes in its own client."""

    @staticmethod
    def selects(filters, paths):
        for path in paths:
            selected = False
            for pattern in filters:
                negative = pattern.startswith('!')
                glob = pattern[1:] if negative else pattern
                # GitHub's **/ also matches zero directory components.
                if fnmatch.fnmatchcase(path, glob) or fnmatch.fnmatchcase(path, glob.replace('/**/', '/')):
                    selected = not negative
            if selected:
                return True
        return False

    def test_browser_workflows_ignore_unrelated_changes_and_keep_own_source_and_packages(self):
        unrelated = [
            '.github/workflows/browser-client.yml', '.github/workflows/browser-direct-client.yml',
            '.github/native-tests.json', 'tools/native-tests/select.py',
            'tools/branch-cleanup/cleanup.py', 'tests/branch-cleanup-test.py',
            'libraries/networking/src/NodeList.cpp', 'libraries/shared/src/shared/WebRTC.h',
            'domain-server/src/DomainServer.cpp', 'assignment-client/src/Agent.cpp',
            'cmake/macros/TargetDataChannel.cmake', 'tests/browser-direct-transport/main.cpp',
            'ios/tests/run-tests.sh', 'android/app/src/Main.java', 'docs/BRANCH_WORKFLOW.md',
            'script-archive/marketplace/S3Server/package-lock.json',
        ]
        for filename, root, events in (
                ('browser-client.yml', 'browser-client', ('pull_request',)),
                ('browser-direct-client.yml', 'browser-direct-client', ('pull_request', 'push'))):
            source = (WORKFLOW_DIRECTORY / filename).read_text()
            for event in events:
                filters = workflow_events(source)[event]['paths']
                with self.subTest(workflow=filename, event=event):
                    self.assertFalse(self.selects(filters, unrelated))
                    for path in unrelated:
                        self.assertFalse(self.selects(filters, [path]), path)
                    for suffix in ('src/main.ts', 'gateway/server.mjs', 'tests/behavior.test.ts',
                                   'public/model.glb', 'package.json', 'package-lock.json'):
                        self.assertTrue(self.selects(filters, [f'{root}/{suffix}']), suffix)
                    for suffix in ('README.md', 'docs/nested/guide.md', 'guide.mdx'):
                        self.assertFalse(self.selects(filters, [f'{root}/{suffix}']), suffix)
                    self.assertTrue(self.selects(filters, [*unrelated, f'{root}/src/main.ts']))
                    other = 'browser-direct-client' if root == 'browser-client' else 'browser-client'
                    self.assertFalse(self.selects(filters, [f'{other}/package-lock.json']))

    def test_atomic_diagnostic_requires_a_changed_browser_laboratory_input(self):
        events = workflow_events((WORKFLOW_DIRECTORY / 'browser-client-atomic-settings.yml').read_text())
        self.assertNotIn('pull_request', events)
        filters = events['push']['paths']
        self.assertTrue(all(not value.startswith('!') and value.startswith('browser-client/') for value in filters))
        self.assertTrue(self.selects(filters, ['browser-client/lab/atomic-provisioning/stage.py']))
        self.assertTrue(self.selects(filters, ['browser-client/lab/manage.py']))
        for path in ('.github/workflows/browser-client-atomic-settings.yml', 'tools/branch-cleanup/cleanup.py',
                     'ios/Interface.mm', 'browser-client/src/world.ts', 'browser-client/README.md'):
            self.assertFalse(self.selects(filters, [path]), path)


class LightweightWorkflowContracts(unittest.TestCase):
    def test_documentation_changes_use_lightweight_checks(self):
        documentation = DOCUMENTATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('workflow_call:', documentation)
        self.assertIn('--all', documentation)
        self.assertIn("tests/check-documentation.py", documentation)
        self.assertIn("timeout-minutes: 5", documentation)
        self.assertIn("persist-credentials: false", documentation)

    def test_markdown_pushes_skip_expensive_shared_checks(self):
        for path in (WORKFLOW, PARENT_QUALIFICATION_WORKFLOW, CODEQL_WORKFLOW):
            source = path.read_text(encoding="utf-8")
            self.assertEqual(workflow_events(source)['push']['paths-ignore'], ['**/*.md'])
        source = CODEQL_WORKFLOW.read_text(encoding="utf-8")
        if codeql_generation(self, source) in {'results', 'retarget-results', 'pinned-results', 'metadata-pinned-results', 'scheduling-pinned-results'}:
            # Required context is published for docs; the immutable selector
            # omits both analyzer jobs, rather than omitting the entire check.
            self.assertNotIn('paths-ignore', workflow_events(source)['pull_request'])
            self.assertEqual(workflow_data(source)['jobs']['analyze']['if'], codeql_analyze_condition(self, source))
        else:
            self.assertEqual(workflow_events(source)['pull_request']['paths-ignore'], ['**/*.md'])

    def test_app_test_workflows_exclude_markdown(self):
        aggregate = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text(encoding="utf-8")
        assert_project_caller_routing(self, aggregate)
        self.assertIn("uses: ./.github/workflows/project-tests.yml", aggregate)
        for workflow in (IOS_WORKFLOW, MACOS_WORKFLOW):
            if workflow.exists():
                source = workflow.read_text(encoding="utf-8")
                if has_automatic_app_trigger(source):
                    self.assertRegex(source, r"[\"']!\*\*/\*\.md[\"']", workflow.name)

    def test_manual_app_workflows_do_not_need_nonexistent_pr_filters(self):
        self.assertFalse(has_automatic_app_trigger("on:\n  workflow_dispatch:\n"))
        self.assertTrue(has_automatic_app_trigger("on:\n  pull_request:\n"))
        self.assertTrue(has_automatic_app_trigger("on:\n  push:\n"))

    def test_canonical_runner_inventory_covers_descendants_and_is_governed(self):
        config = (ROOT / ".github/actionlint.yaml").read_text()
        labels = set(re.findall(r"(?m)^    - (overte-[a-z0-9-]+)$", config))
        self.assertEqual(labels, {
            "overte-android-build", "overte-android-phone-build",
            "overte-android-phone-emulator", "overte-android-phone-release",
            "overte-android-release", "overte-pico4-device", "overte-ios-ipad",
        })
        workflow = (WORKFLOW_DIRECTORY / "workflow-security.yml").read_text()
        self.assertIn("actionlint -config-file .github/actionlint.yaml -no-color", workflow)
        self.assertNotIn("ACTIONLINT_SELF_HOSTED_LABELS", workflow)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1 python3 tests/workflow-contract-test.py", workflow)
        policy = (ROOT / "tools/branch-policy/check.py").read_text().split("PRIVILEGED_PATHS = (", 1)[1].split(")", 1)[0]
        self.assertIn('".github/actionlint.yaml"', policy)
        reuse = json.loads((ROOT / ".github/sync-test-reuse.json").read_text())
        self.assertIn(".github/actionlint.yaml", reuse["qualified_inputs"])
        self.assertIn(".github/actionlint.yaml", reuse["required_qualified_inputs"])


class WorkflowStorageContracts(unittest.TestCase):
    def test_artifact_uploads_have_explicit_bounded_retention(self):
        upload_count = 0
        for workflow in sorted(WORKFLOW_DIRECTORY.glob("*.yml")):
            lines = workflow.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if not re.match(r"^\s*uses:\s*actions/upload-artifact@", line):
                    continue
                upload_count += 1
                uses_indent = len(line) - len(line.lstrip())
                block = []
                for candidate in lines[index + 1 :]:
                    if candidate.strip():
                        indent = len(candidate) - len(candidate.lstrip())
                        if indent < uses_indent:
                            break
                    block.append(candidate)
                retentions = [
                    int(match.group(1))
                    for candidate in block
                    if (match := re.match(r"^\s*retention-days:\s*(\d+)\s*$", candidate))
                ]
                self.assertEqual(
                    len(retentions),
                    1,
                    f"{workflow.name}: each artifact upload needs one retention-days value",
                )
                self.assertLessEqual(retentions[0], artifact_retention_limit(workflow.name, block), workflow.name)
                self.assertGreaterEqual(retentions[0], 1, workflow.name)
        self.assertGreater(upload_count, 0)

    def test_source_checkpoint_retention_exception_cannot_cover_other_artifacts(self):
        checkpoint = ["build-ios/qt-source-checkpoint/checkpoint.tar.gz",
                      "build-ios/qt-source-checkpoint/manifest.json"]
        self.assertEqual(artifact_retention_limit("ios-qt-source.yml", checkpoint), 90)
        self.assertEqual(artifact_retention_limit("other.yml", checkpoint), 30)
        self.assertEqual(artifact_retention_limit("ios-qt-source.yml", checkpoint[:1]), 30)
        self.assertEqual(artifact_retention_limit("ios-qt-source.yml", ["build-ios/log.txt"]), 30)

    def test_native_sccache_github_backend_stays_disabled(self):
        sources = "\n".join(
            workflow.read_text(encoding="utf-8")
            for workflow in sorted(WORKFLOW_DIRECTORY.glob("*.yml"))
        )
        self.assertNotIn("SCCACHE_GHA_ENABLED", sources)


class CodeQLWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CODEQL_WORKFLOW.read_text(encoding="utf-8")

    def test_pilot_is_github_hosted_and_bounded(self):
        self.assertIn("runs-on: ubuntu-24.04", self.source)
        self.assertNotIn("self-hosted", self.source)
        self.assertIn("timeout-minutes: 30", self.source)
        self.assertIn("language: ${{ fromJSON(needs.select.outputs.languages) }}", self.source)
        self.assertEqual(workflow_data(self.source)['jobs']['analyze']['if'],
                         codeql_analyze_condition(self, self.source))
        self.assertIn("build-mode: none", self.source)

    def test_permissions_are_least_privilege(self):
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        analyze = self.source.split("  analyze:", 1)[1]
        self.assertRegex(
            analyze,
            r"(?m)^    permissions:\n      contents: read\n      security-events: write$",
        )
        self.assertNotRegex(self.source, r"(?m)^\s+(actions|attestations|id-token|packages): write$")

    def test_actions_are_fresh_full_sha_pins(self):
        actions = ACTION_USE.findall(self.source)
        generation=codeql_generation(self,self.source)
        local=[action for action in actions if action.startswith('./')]
        self.assertEqual(local,['./.github/workflows/pr-metadata-context.yml']
                         if generation in {'metadata-pinned-results', 'scheduling-pinned-results'} else [])
        self.assertEqual(len(actions),8 if generation in {'metadata-pinned-results', 'scheduling-pinned-results'} else
            7 if generation in {'results','retarget-results','pinned-results'} else 5)
        self.assertEqual([action for action in actions if action not in local and not FULL_SHA_ACTION.fullmatch(action)], [])
        codeql = [action for action in actions if action.startswith("github/codeql-action/")]
        self.assertEqual(
            codeql,
            [
                "github/codeql-action/init@cdf488f595d80d6e07e03d4674febd5ab45fa938",
                "github/codeql-action/analyze@cdf488f595d80d6e07e03d4674febd5ab45fa938",
            ],
        )

    def test_checkout_is_credential_free_and_default_setup_is_not_mixed_in(self):
        self.assertIn("persist-credentials: false", self.source)
        self.assertNotIn("autobuild", self.source)

    def test_selector_reads_trusted_policy_and_exact_immutable_candidate(self):
        selector = self.source.split('  select:', 1)[1].split('  analyze:', 1)[0]
        self.assertIn('ref: ${{ github.event.repository.default_branch }}', selector)
        self.assertIn('path: trusted', selector)
        self.assertIn('path: candidate', selector)
        self.assertIn('fetch-depth: 2', selector)
        self.assertEqual(selector.count('persist-credentials: false'), 2)
        self.assertIn('CANDIDATE_SHA: ${{ github.sha }}', selector)
        self.assertIn('BASE_SHA: ${{ github.event.pull_request.base.sha || github.event.before || github.sha }}', selector)
        self.assertIn('python3 trusted/tools/repository-checks/codeql.py', selector)
        self.assertIn('--root candidate --base-sha "$BASE_SHA" --candidate-sha "$CANDIDATE_SHA"', selector)
        self.assertIn('--event "$EVENT_NAME" > codeql-plan.json', selector)
        self.assertIn('cron: "17 3 * * 4"', self.source)

    def test_selected_analyses_fail_closed_in_final_aggregate(self):
        aggregate = self.source.split('  codeql-checks:', 1)[1]
        self.assertIn('if: always()', aggregate)
        self.assertIn('needs: [select, analyze]', aggregate)
        selected = codeql_generation(self, self.source) in {'retarget-results', 'pinned-results', 'metadata-pinned-results', 'scheduling-pinned-results'}
        job = workflow_data(self.source)['jobs']['codeql-checks']
        self.assertEqual(job['if'], "always() && (needs.select.result != 'success' || needs.select.outputs.metadata_only != 'true')"
                         if selected else 'always()')
        self.assertEqual(job['name'], "${{ needs.select.result == 'success' && needs.select.outputs.metadata_only == 'true' && "
                         "'codeql-security-results (metadata unchanged)' || 'codeql-security-results' }}"
                         if selected else 'codeql-security-results')
        steps = workflow_data(self.source)['jobs']['codeql-checks']['steps']
        script = next(step['run'] for step in steps if step['name'] == 'Require every selected analysis')
        for selected in ('success', 'failure', 'cancelled', 'skipped'):
            for scan in ('true', 'false', ''):
                for analysis in ('success', 'failure', 'cancelled', 'skipped'):
                    env = dict(os.environ, SELECT_RESULT=selected, SCAN=scan, ANALYZE_RESULT=analysis)
                    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True)
                    expected = selected == 'success' and (scan, analysis) in {
                        ('true', 'success'), ('false', 'skipped')}
                    self.assertEqual(result.returncode == 0, expected, (selected, scan, analysis))


    def test_selected_results_are_independent_and_cannot_bypass_the_truth_table(self):
        if codeql_generation(self, self.source) not in {'results', 'retarget-results', 'pinned-results', 'metadata-pinned-results', 'scheduling-pinned-results'}:
            self.skipTest("Selected-result generation is covered by its staged workflow contracts")
        workflow = workflow_data(self.source)
        job = workflow['jobs']['codeql-checks']
        self.assertEqual(job['permissions'], {'contents': 'read', 'actions': 'read',
                         'pull-requests': 'read', 'security-events': 'read'})
        steps = job['steps']
        self.assertEqual(steps[0]['name'], 'Require every selected analysis')
        trusted = next(step for step in steps if step['name'] == 'Check out trusted selected-result policy')
        self.assertEqual(trusted['with']['ref'], '${{ github.event.repository.default_branch }}')
        self.assertEqual(trusted['with']['path'], 'trusted')
        candidate = next(step for step in steps if step['name'] == 'Read the exact candidate for independent result selection')
        self.assertEqual(candidate['with']['ref'], '${{ github.sha }}')
        verify = steps[-1]
        self.assertEqual(verify['name'], 'Require current selected-language security results')
        self.assertIn('trusted/tools/repository-checks/codeql_results.py', verify['run'])
        for flag in ('--root candidate', '--event-file "$GITHUB_EVENT_PATH"'):
            self.assertIn(flag, verify['run'])
        self.assertEqual(verify['env']['GH_TOKEN'], '${{ github.token }}')
        self.assertEqual(verify['env']['CODEQL_EXPECTED_LANGUAGES'], '${{ needs.select.outputs.languages }}')
        self.assertNotIn('continue-on-error:', self.source)
        # The named required context must also exist for documentation-only PRs.
        triggers = workflow.get('on', workflow.get(True))
        self.assertNotIn('paths-ignore', triggers['pull_request'])
        self.assertEqual(triggers['push']['paths-ignore'], ['**/*.md'])
        expected = {'main', 'apple-main', 'apple-ios', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico'}
        self.assertEqual(set(triggers['push']['branches']), expected)
        self.assertEqual(set(triggers['pull_request']['branches']), expected)


@unittest.skipIf(
    CODEQL_WORKFLOW.read_text() == (ROOT / "tools/repository-checks/workflows/codeql-results.yml").read_text(),
    "The identical deployed generation is already covered by the active workflow contracts",
)
class SelectedCodeQLResultWorkflowContracts(CodeQLWorkflowContracts):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tools/repository-checks/workflows/codeql-results.yml").read_text()


class RetargetCodeQLResultWorkflowContracts(CodeQLWorkflowContracts):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml').read_text()

    def test_retarget_and_metadata_route_preserve_existing_analysis_and_security_assertions(self):
        previous = workflow_data((ROOT / 'tools/repository-checks/workflows/codeql-results.yml').read_text())
        successor = workflow_data(self.source)
        triggers = successor.get('on', successor.get(True))
        self.assertEqual(triggers['pull_request']['types'], ['opened', 'reopened', 'synchronize', 'edited'])
        ordinary = workflow_data((ROOT / 'tools/repository-checks/workflows/codeql-results.yml').read_text())
        normal_triggers = ordinary.get('on', ordinary.get(True))
        self.assertEqual({k: v for k, v in triggers['pull_request'].items() if k != 'types'}, normal_triggers['pull_request'])
        self.assertEqual(triggers['push'], normal_triggers['push'])
        self.assertEqual(triggers['schedule'], normal_triggers['schedule'])
        suffix = "-${{ github.event.action == 'edited' && !github.event.changes.base && " \
                 "(github.event.changes.title || github.event.changes.body) && github.run_id || 'qualification' }}"
        self.assertTrue(successor['concurrency']['group'].endswith(suffix))
        self.assertIs(successor['concurrency']['cancel-in-progress'], True)
        self.assertEqual(successor['permissions'], previous['permissions'])
        for name in ('analyze', 'codeql-checks'):
            future, old = dict(successor['jobs'][name]), dict(previous['jobs'][name])
            for key in ('name', 'if'): future.pop(key); old.pop(key)
            self.assertEqual(future, old, 'all actual analysis and security-verification steps must remain unchanged')
        select = successor['jobs']['select']
        self.assertEqual(select['outputs']['metadata_only'], '${{ steps.event.outputs.metadata_only }}')
        classifier = next(step for step in select['steps'] if step.get('id') == 'event')
        self.assertIn('trusted/tools/repository-checks/check.py metadata-event', classifier['run'])
        candidate = next(step for step in select['steps'] if step['name'] == 'Read the exact candidate inventory')
        plan = next(step for step in select['steps'] if step.get('id') == 'plan')
        self.assertLess(select['steps'].index(classifier), select['steps'].index(candidate))
        for step in (candidate, plan): self.assertEqual(step['if'], "steps.event.outputs.metadata_only != 'true'")
        self.assertEqual(plan['env']['BASE_SHA'], '${{ github.event.pull_request.base.sha || github.event.before || github.sha }}')
        self.assertEqual(plan['env']['CANDIDATE_SHA'], '${{ github.sha }}')

class PinnedCodeQLResultWorkflowContracts(CodeQLWorkflowContracts):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml').read_text()

    def test_pinned_successor_changes_only_tool_selection_and_required_version_check(self):
        previous = workflow_data((ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml').read_text())
        successor = workflow_data(self.source)
        steps = previous['jobs']['analyze']['steps']
        initialize = next(step for step in steps if step['name'] == 'Initialize CodeQL')
        initialize['id'] = 'init'
        initialize['with']['tools'] = ('https://github.com/github/codeql-action/releases/download/'
                                      'codeql-bundle-v2.27.2/codeql-bundle-linux64.tar.zst')
        version = {'name': 'Require reviewed CodeQL extractor version',
                   'env': {'CODEQL_VERSION': '${{ steps.init.outputs.codeql-version }}'},
                   'run': 'set -euo pipefail\ntest "$CODEQL_VERSION" = 2.27.2\n'}
        index = next(i for i, step in enumerate(steps) if step['name'] == 'Analyze')
        steps.insert(index, version)
        self.assertEqual(successor, previous)
        # Use the action's URL/toolcache path, without a separate downloader or
        # local archive that would force extraction on every matching cache hit.
        for value, expected in (('2.27.2', True), ('', False), ('2.27.3', False), ('2.27.2-extra', False)):
            result = subprocess.run(['bash', '-c', version['run']],
                                    env=dict(os.environ, CODEQL_VERSION=value), capture_output=True)
            self.assertEqual(result.returncode == 0, expected)


class HistoricalMetadataCodeQLResultWorkflowContracts(CodeQLWorkflowContracts):
    @classmethod
    def setUpClass(cls):
        cls.source = historical_metadata_codeql()


class SchedulingCodeQLResultWorkflowContracts(CodeQLWorkflowContracts):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml').read_text()


class BranchGovernanceWorkflowContracts(unittest.TestCase):
    def test_policy_is_a_native_read_only_pull_request_check(self):
        source = BRANCH_POLICY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", source)
        self.assertNotIn("pull_request_target:", source)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", source)
        self.assertIn("persist-credentials: false", source)
        self.assertRegex(
            source,
            r"(?m)^permissions:\n  contents: read\n  pull-requests: read$",
        )
        self.assertIn("name: branch-policy", source)
        self.assertIn("github.event.pull_request.head.sha", source)
        self.assertIn("github.event.pull_request.head.repo.id", source)
        self.assertIn("github.event.pull_request.base.repo.id", source)
        self.assertIn("github.event.pull_request.user.login", source)
        self.assertIn("github.event.pull_request.user.type", source)
        self.assertIn("github.event.repository.id", source)
        self.assertNotIn("check-runs", source)
        self.assertNotRegex(source, r"(?m)^\s*(checks|pull-requests|contents): write$")

    def test_policy_never_executes_pull_request_policy_or_workflow_changes(self):
        source = BRANCH_POLICY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Check out trusted policy", source)
        self.assertIn("github.event.repository.default_branch", source)
        checkout = source.split("with:", 1)[1].split("- name: Validate", 1)[0]
        self.assertNotIn("github.event.pull_request.head.sha", checkout)
        self.assertIn("pulls/$PULL_REQUEST/files", source)
        self.assertIn("gh api --paginate", source)
        self.assertIn("--jq '.[].filename'", source)
        self.assertNotIn("--paginate --slurp", source)
        self.assertIn("--changed-files-stdin", source)

    def test_governance_actions_are_pinned(self):
        for workflow in (BRANCH_POLICY_WORKFLOW, BRANCH_SYNC_WORKFLOW):
            actions = ACTION_USE.findall(workflow.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(actions), 1)
            self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])

    def test_sync_is_read_only_drift_detection(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("tools/branch-policy/drift.py", source)
        self.assertIn("--expected-parent-sha \"$PUSH_SHA\"", source)
        self.assertIn('--expected-parent-sha "$PUSH_SHA" --observe-push', source)
        strict_tail = source.split('          else\n', 1)[1]
        self.assertNotIn('--observe-push', strict_tail)
        self.assertIn("github.event.repository.default_branch", source)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", source)
        self.assertNotIn("actions/create-github-app-token@", source)
        self.assertNotIn("BRANCH_SYNC_APP", source)
        self.assertNotIn("${{ secrets.", source)
        self.assertNotIn("gh pr", source)
        self.assertNotIn("--auto", source)
        self.assertNotIn("check-runs", source)
        self.assertIn("group: branch-synchronization-${{ github.ref_name }}", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertNotIn("Skipping $parent -> $child", source)
        self.assertNotIn("continue", source)

    def test_multiple_prs_cannot_be_selected_or_merged(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in ("gh pr list", "gh pr create", "gh pr merge", "pulls?", ".[0]"):
            self.assertNotIn(forbidden, source)

    def test_wrong_app_or_author_cannot_authorize_sync(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in ("create-github-app-token", "client-id", "private-key", "author", "login"):
            self.assertNotIn(forbidden, source)


    def test_retired_desktop_branches_have_no_workflow_routes(self):
        for path in WORKFLOW_DIRECTORY.glob("*.yml"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertNotIn("linux-main", source)
                self.assertNotIn("windows-main", source)
        policy = json.loads((ROOT / ".github/branch-policy.json").read_text())
        self.assertEqual(policy["branches"]["main"]["children"], ["android-main", "apple-main"])
        for platform in ("linux", "windows"):
            self.assertTrue((ROOT / "tests/device/adapters/desktop_oculix" / f"{platform}.json").is_file())

    def test_sync_reuse_gate_is_trusted_terminal_and_fail_closed(self):
        source = SYNC_REUSE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", source)
        self.assertNotIn("paths:", source)
        self.assertIn("timeout-minutes: 35", source)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("dispatch-and-wait", source)
        self.assertIn('--gate-run-id "$GITHUB_RUN_ID"', source)
        self.assertIn('--gate-run-attempt "$GITHUB_RUN_ATTEMPT"', source)
        self.assertIn("steps.inspect.outputs.mode != 'ordinary'", source)
        self.assertNotIn("github.event.pull_request.head.sha }}\n          path:", source)
        self.assertNotIn("${{ secrets.", source)

    def test_candidate_execution_is_isolated_read_only(self):
        import yaml
        source = SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8")
        workflow = yaml.safe_load(source)
        selected_sync_recipe()  # Also checks the complete deployed tuple.
        permissions = {'actions': 'read', 'contents': 'read', 'pull-requests': 'read'}
        staged = ROOT / 'tools/repository-checks/workflows/sync-ci-selection.yml'
        if source == staged.read_text(): permissions['checks'] = 'read'
        self.assertEqual(workflow['permissions'], permissions)
        self.assertNotRegex(source, r"(?m)^\s+[a-z-]+: write$")
        self.assertNotIn("secrets.", source)
        steps = workflow['jobs']['validate']['steps']
        checkouts = [step['with'] for step in steps if step.get('uses', '').startswith('actions/checkout@')]
        self.assertEqual([(step['path'], step['ref'], step['persist-credentials']) for step in checkouts],
                         [('trusted', 'main', False), ('candidate', '${{ inputs.expected_merge_sha }}', False)])
        staged = ROOT / 'tools/repository-checks/workflows/sync-ci-selection.yml'
        if selected_sync_recipe():
            spec = importlib.util.spec_from_file_location(
                'sync_workflow_packages', ROOT / 'tools/repository-checks/package_checks.py')
            packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
            self.assertIn(reviewed_package_generation(),SELECTED_SYNC_GENERATIONS)
            self.assertIn("steps.select.outputs.full_host == 'true'", source)
            self.assertIn('--expected-selection "$EXPECTED_SELECTION"', source)
        else:
            self.assertIn("inputs.mode == 'fallback'", source)
        self.assertIn('GH_TOKEN: ""', source)
        self.assertIn('GITHUB_TOKEN: ""', source)
        self.assertNotIn('candidate/tests/run-project-tests.py', source)
        self.assertNotIn('python tests/run-project-tests.py', source)
        for step in steps:
            if 'trusted/tools/test-evidence/validate-sync.py' in step.get('run', ''):
                self.assertNotEqual(step.get('working-directory'), 'candidate')
                self.assertIn('--candidate candidate', step['run'])
                for field in ('base-sha', 'head-sha', 'merge-sha'):
                    self.assertIn('--' + field, step['run'])
                self.assertIn('--receipt build/test-results/sync-validation.json', step['run'])

    def test_sync_reuse_has_no_readiness_rerun_or_postvalidation_cancellation(self):
        import yaml
        source = SYNC_REUSE_WORKFLOW.read_text(encoding="utf-8")
        workflow = yaml.safe_load(source)
        triggers = workflow.get('on', workflow.get(True))
        self.assertEqual(triggers['pull_request_target']['types'], ['opened', 'reopened', 'synchronize', 'edited'])
        self.assertNotIn('cancel-redundant', source)
        self.assertNotIn('--window', source)
        self.assertEqual(source.count('gate.py dispatch-and-wait'), 1)
        self.assertTrue(workflow['concurrency']['cancel-in-progress'])

    def test_staged_sync_selects_before_setup_and_binds_actual_execution(self):
        staged = ROOT / 'tools/repository-checks/workflows/sync-ci-selection.yml'
        source = staged.read_text()
        workflow = workflow_data(source)
        self.assertEqual(workflow['permissions'], {'actions': 'read', 'checks': 'read', 'contents': 'read', 'pull-requests': 'read'})
        self.assertEqual(set(workflow_events(source)), {'workflow_dispatch'})
        steps = workflow['jobs']['validate']['steps']
        selected = next(step for step in steps if step.get('id') == 'select')
        self.assertIn('--select-only --output "$GITHUB_OUTPUT"', selected['run'])
        self.assertIn('python3 -B trusted/tools/test-evidence/validate-sync.py', selected['run'])
        candidate = next(step for step in steps if step.get('with', {}).get('path') == 'candidate')
        self.assertEqual(candidate['with']['fetch-depth'], 2)
        self.assertFalse(candidate['with']['persist-credentials'])
        self.assertLess(steps.index(candidate), steps.index(selected))
        old = workflow_data((ROOT / 'tools/repository-checks/workflows/packages/sync-validation.yml').read_text())
        old_steps = {step['name']: step for step in old['jobs']['validate']['steps']}
        for name in ('Set up candidate Python', 'Set up candidate Node.js', 'Set up candidate Java',
                     'Install candidate host prerequisites', 'Prepare isolated shared and product Python validators'):
            actual = next(step for step in steps if step['name'] == name)
            self.assertLess(steps.index(selected), steps.index(actual))
            previous, current = dict(old_steps[name]), dict(actual)
            previous.pop('if'); current.pop('if')
            self.assertEqual(previous, current)
            self.assertIn("&& !(steps.select.outputs.lane == 'verified-empty' && steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.empty_setup != '')", actual['if'])
        for name in ('Set up candidate Java', 'Install candidate host prerequisites'):
            self.assertEqual(next(step for step in steps if step['name'] == name)['if'],
                             "(steps.select.outputs.consumer_setup != 'none' || steps.select.outputs.native_setup == '') && steps.select.outputs.full_host == 'true' && !(steps.select.outputs.lane == 'verified-empty' && steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.empty_setup != '')")
        executions = [step for step in steps if 'trusted/tools/test-evidence/validate-sync.py' in step.get('run', '')
                      and step.get('id') != 'select']
        self.assertEqual(len(executions), 3)
        self.assertEqual({step['name'] for step in executions}, {
            'Verify bounded synchronization without product setup',
            'Verify exact candidate suites and complete runtime identity',
            'Validate the exact unchanged synchronization without test execution'})
        for step in executions:
            self.assertIn('--expected-selection "$EXPECTED_SELECTION"', step['run'])
            self.assertEqual(step['env']['EXPECTED_SELECTION'], '${{ steps.select.outputs.selection }}')
            if step['name'] == 'Validate the exact unchanged synchronization without test execution':
                self.assertEqual(step['if'], "steps.select.outputs.lane == 'verified-empty'")
                self.assertEqual(step['env']['EXPECTED_EMPTY_SETUP'], '${{ steps.select.outputs.empty_setup }}')
                self.assertTrue(step['run'].startswith('python3 -B '))
                self.assertIn('--expected-empty-setup "$EXPECTED_EMPTY_SETUP"', step['run'])
                self.assertNotIn('--expected-native-setup', step['run'])
                self.assertNotIn('SYNC_VALIDATOR_PYTHON', step['env'])
            elif step['name'] == 'Verify exact candidate suites and complete runtime identity':
                self.assertIn("steps.select.outputs.lane != 'verified-empty'", step['if'])
                self.assertEqual(step['env']['EXPECTED_NATIVE_SETUP'], '${{ steps.select.outputs.native_setup }}')
                self.assertIn('--expected-native-setup "$EXPECTED_NATIVE_SETUP"', step['run'])
        self.assertNotIn('candidate/tests/run-project-tests.py', source)

    def test_selected_sync_contract_rejects_foreign_mode_and_alias_recipes(self):
        # A legitimate historical selected recipe remains valid when a newer
        # canonical recipe is merely staged. Neither hash nor mode is inferred
        # from a scheduling atom or a mutable file of the same name.
        self.assertIn(reviewed_package_generation(), SELECTED_SYNC_GENERATIONS)
        self.assertTrue(selected_sync_recipe())
        raw = SYNC_VALIDATION_WORKFLOW.read_bytes()
        with tempfile.TemporaryDirectory(prefix='overte-sync-contract-') as directory:
            candidate = Path(directory) / 'sync-validation.yml'
            for change in ('foreign', 'mode', 'alias'):
                if candidate.exists() or candidate.is_symlink(): candidate.unlink()
                candidate.write_bytes(raw + (b'\n# foreign source\n' if change == 'foreign' else b''))
                candidate.chmod(0o644)
                if change == 'mode': candidate.chmod(0o755)
                elif change == 'alias': candidate.unlink(); candidate.symlink_to(SYNC_VALIDATION_WORKFLOW)
                with self.subTest(change=change), mock.patch.object(
                        sys.modules[__name__], 'SYNC_VALIDATION_WORKFLOW', candidate), self.assertRaises(AssertionError):
                    sync_condition('legacy', 'selected')

    def test_staged_sync_has_one_exact_complete_generation(self):
        spec = importlib.util.spec_from_file_location(
            'staged_sync_packages', ROOT / 'tools/repository-checks/package_checks.py')
        packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
        packages, tree = prospective_package_tree()
        self.assertEqual(packages.validate_tree_wiring(tree), 'protected-producer-original-default-v1')
        self.assertIn('protected-producer-original-default-v1', SELECTED_SYNC_GENERATIONS)
        self.assertIn(reviewed_package_generation(), SELECTED_SYNC_GENERATIONS)
        deployed = next(row for row in packages.workflow_generations()
                        if row['name'] == reviewed_package_generation())['workflows']
        self.assertEqual(packages.validate_tree_wiring(deployed), reviewed_package_generation())
        if deployed['.github/workflows/sync-validation.yml'] != tree['.github/workflows/sync-validation.yml']:
            mixed = {path: dict(entry) for path, entry in deployed.items()}
            mixed['.github/workflows/sync-validation.yml'] = dict(tree['.github/workflows/sync-validation.yml'])
            with self.assertRaises(ValueError): packages.validate_tree_wiring(mixed)
        for relative in tree:
            changed = {path: dict(entry) for path, entry in tree.items()}
            changed[relative]['sha'] = '0' * 40
            with self.subTest(path=relative), self.assertRaises(ValueError):
                packages.validate_tree_wiring(changed)

    def test_verified_empty_sync_conditions_require_the_complete_installed_generation(self):
        packages, future = prospective_package_tree()
        generation = reviewed_package_generation()
        deployed = next(row['workflows'] for row in packages.workflow_generations()
                        if row['name'] == generation)
        self.assertEqual(packages.validate_tree_wiring(deployed), generation)
        product = "steps.select.outputs.lane != 'legacy-bounded'"
        setup = "steps.select.outputs.full_host == 'true'"
        if generation == 'protected-producer-original-default-v1':
            self.assertEqual(deployed, future)
            self.assertEqual(SYNC_VALIDATION_WORKFLOW.read_bytes(),
                (ROOT / 'tools/repository-checks/workflows/sync-ci-selection.yml').read_bytes())
            product += " && steps.select.outputs.lane != 'verified-empty'"
            setup = "(steps.select.outputs.consumer_setup != 'none' || steps.select.outputs.native_setup == '') && " + setup
            setup += " && !(steps.select.outputs.lane == 'verified-empty' && steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.empty_setup != '')"
        else:
            self.assertNotEqual(deployed['.github/workflows/sync-validation.yml'],
                                future['.github/workflows/sync-validation.yml'])
        self.assertEqual(sync_condition('legacy-product', "steps.select.outputs.lane != 'legacy-bounded'"), product)
        self.assertEqual(sync_condition('legacy-setup', "steps.select.outputs.full_host == 'true'", setup=True), setup)
        self.assertEqual(sync_condition('legacy-bounded', "steps.select.outputs.lane == 'legacy-bounded'"),
                         "steps.select.outputs.lane == 'legacy-bounded'")
        # A scheduling suffix grants no recipe authority: every future endpoint
        # remains mandatory with its complete ordinary mode/type/hash identity.
        for relative in future:
            for change in ('foreign', 'mode', 'alias', 'missing'):
                changed = {path: dict(entry) for path, entry in future.items()}
                if change == 'foreign': changed[relative]['sha'] = '0' * 40
                elif change == 'mode': changed[relative]['mode'] = '100755'
                elif change == 'alias': changed[relative]['mode'] = '120000'
                else: del changed[relative]
                with self.subTest(path=relative, change=change), self.assertRaises(ValueError):
                    packages.validate_tree_wiring(changed)

    def test_qualification_is_exact_push_only_and_bounded(self):
        source = PARENT_QUALIFICATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("push:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("workflow_dispatch:", source)
        self.assertEqual(workflow_events(source)['push']['branches'], ['main', 'android-main', 'android-vr', 'apple-main'])
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("retention-days: 4", source)

    def test_reused_shared_qualification_still_runs_product_suites(self):
        import yaml
        source = SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8")
        steps = yaml.safe_load(source)['jobs']['validate']['steps']
        product = next(step for step in steps if step.get('name') == 'Verify exact candidate suites and complete runtime identity')
        self.assertEqual(product['if'], sync_condition(
            "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')", "steps.select.outputs.lane != 'legacy-bounded'"))
        self.assertIn('--mode "$MODE" --profile "$PROFILE"', product['run'])
        self.assertEqual(product['env']['MODE'], '${{ inputs.mode }}')
        # The trusted consumer, rather than a mutable candidate runner, owns
        # execution of all declared product suites on reuse and fallback alike.
        consumer = ast.parse((ROOT / 'tools/test-evidence/validate-sync.py').read_text())
        executions = [node for node in ast.walk(consumer) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                      and (node.func.value.id, node.func.attr) == ('execution', 'execute')]
        self.assertEqual(len(executions), 1)
        self.assertTrue(next(item.value for item in executions[0].keywords if item.arg == 'include_platform').value)

    def test_project_workflow_is_reusable_with_single_caller_routing(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", source)
        self.assertNotIn("run_full", source)
        self.assertIn("needs: route", source)
        self.assertIn('--event "$GITHUB_EVENT_PATH"', source)
        self.assertNotIn("pull_request:", source)
        aggregate = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text()
        assert_project_caller_routing(self, aggregate)
        pull_request = aggregate.split("  pull_request:", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertNotIn("paths", pull_request)
        self.assertIn("edited", pull_request)


class RulesetManifestContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = {
            name: json.loads((RULESETS / filename).read_text(encoding="utf-8"))
            for name, filename in RULESET_FILES.items()
        }
        cls.manifests.update({
            name: json.loads(path.read_text(encoding="utf-8"))
            for name, path in STAGED_RULESET_FILES.items()
        })

    @staticmethod
    def rule(manifest, rule_type):
        return next(rule for rule in manifest["rules"] if rule["type"] == rule_type)

    def test_all_persistent_rulesets_are_complete_and_versioned(self):
        versioned = []
        for path in RULESETS.glob("*.json"):
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if "target" in candidate:
                versioned.append(path.name)

        self.assertEqual(sorted(versioned), sorted(RULESET_FILES.values()))
        self.assertEqual(set(self.manifests), set(RULESET_FILES) | set(STAGED_RULESET_FILES))
        for name, manifest in self.manifests.items():
            self.assertEqual(manifest["name"], name)
            self.assertIn(manifest["target"], ("branch", "tag"))
            self.assertEqual(manifest["enforcement"], "active")
            self.assertEqual(manifest["bypass_actors"], [])
            self.assertEqual(manifest["conditions"]["ref_name"]["exclude"], [])
            self.assertTrue(manifest["conditions"]["ref_name"]["include"])
            self.assertTrue(manifest["rules"])

    def test_required_checks_are_strict_and_bound_to_github_actions(self):
        expected = {
            "Android target branch topology": "Enforce Android parent sync path",
            "Apple target branch topology": "Enforce apple-main sync path",
            "Permanent branch governance": "branch-policy",
            "Selected CodeQL security results on main": "codeql-security-results",
        }
        for name, context in expected.items():
            parameters = self.rule(
                self.manifests[name], "required_status_checks"
            )["parameters"]
            self.assertTrue(parameters["strict_required_status_checks_policy"])
            self.assertFalse(parameters["do_not_enforce_on_create"])
            expected_checks = [{"context": context, "integration_id": 15368}]
            if name == "Apple target branch topology":
                expected_checks.append(
                    {"context": "ios-device-build", "integration_id": 15368}
                )
            if name == "Permanent branch governance":
                expected_checks.insert(0, {"context": "dependency-release-policy", "integration_id": 15368})
                expected_checks.append(
                    {"context": "sync-test-reuse", "integration_id": 15368}
                )
                expected_checks.append(
                    {"context": "repository-checks", "integration_id": 15368}
                )
            self.assertEqual(parameters["required_status_checks"], expected_checks)
            if name == "Selected CodeQL security results on main":
                self.assertEqual(self.manifests[name]["conditions"]["ref_name"],
                                 {"include": ["refs/heads/" + branch for branch in (
                                     "main", "apple-main", "apple-ios", "android-main",
                                     "android-phone", "android-vr", "android-vr-pico")],
                                  "exclude": []})
                self.assertEqual(len(self.manifests[name]["rules"]), 1)


    def test_solo_profile_is_active_without_locking_out_the_maintainer(self):
        solo = json.loads(
            (RULESETS / "review-profiles/solo-maintainer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(solo["required_approving_review_count"], 0)
        self.assertFalse(solo["require_last_push_approval"])
        self.assertEqual(solo["allowed_merge_methods"], ["merge"])
        for name in (
            "Android target branch topology",
            "Apple target branch topology",
            "Permanent branch governance",
        ):
            self.assertEqual(
                self.rule(self.manifests[name], "pull_request")["parameters"], solo
            )

    def test_independent_reviewer_profile_is_ready_but_not_active(self):
        independent = json.loads(
            (RULESETS / "review-profiles/independent-reviewer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(independent["required_approving_review_count"], 1)
        self.assertTrue(independent["dismiss_stale_reviews_on_push"])
        self.assertTrue(independent["require_last_push_approval"])
        self.assertTrue(independent["required_review_thread_resolution"])
        for manifest in self.manifests.values():
            for rule in manifest["rules"]:
                if rule["type"] == "pull_request":
                    self.assertNotEqual(rule["parameters"], independent)

    def test_governed_refs_retain_deletion_and_non_fast_forward_protection(self):
        for name in (
            "Android target branch topology",
            "Apple target branch topology",
            "Immutable Android, canonical, and archive tags",
            "Immutable Pico 4 release and dependency tags",
            "Permanent branch governance",
        ):
            rule_types = {rule["type"] for rule in self.manifests[name]["rules"]}
            self.assertIn("deletion", rule_types)
            self.assertIn("non_fast_forward", rule_types)

    def test_used_release_dependency_and_archive_tag_namespaces_are_protected(self):
        protected = set()
        for name, manifest in self.manifests.items():
            if manifest["target"] == "tag":
                protected.update(manifest["conditions"]["ref_name"]["include"])
        self.assertEqual(
            protected,
            {
                "refs/tags/[0-9]*",
                "refs/tags/v[0-9]*",
                "refs/tags/android-phone-v*",
                "refs/tags/android-phone-16k-deps-v*",
                "refs/tags/archive/**",
                "refs/tags/pico4-v*-rc.*",
                "refs/tags/pico4-preview-*",
                "refs/tags/pico4-deps-v*",
            },
        )

    def test_signed_commits_are_not_required(self):
        for manifest in self.manifests.values():
            self.assertNotIn(
                "required_signatures", {rule["type"] for rule in manifest["rules"]}
            )

    def test_repository_merge_settings_match_transition_policy(self):
        settings = json.loads(
            (RULESETS / "repository-merge-settings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(settings["repository"], "noah-l-frank/overte")
        self.assertEqual(
            settings["settings"],
            {
                "allow_auto_merge": False,
                "allow_merge_commit": True,
                "allow_rebase_merge": False,
                "allow_squash_merge": False,
                "allow_update_branch": False,
                "delete_branch_on_merge": False,
            },
        )


class ArchivedRefRetirementContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = RULESETS / "retirements/archived-branches.json"
        cls.plan = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_temporary_ruleset_is_retired_without_bypass(self):
        retirement = self.plan["ruleset_retirement"]
        self.assertEqual(retirement["name"], "Archived branches")
        self.assertEqual(retirement["operation"], "delete_ruleset_by_freshly_resolved_id")
        self.assertEqual(retirement["expected_current"]["bypass_actors"], [])
        self.assertIn("never use a bypass", retirement["sequence"])
        self.assertFalse((RULESETS / "archived-branches.json").exists())

    def test_all_exact_archive_refs_are_unique_and_batched_4_4_4_1(self):
        refs = self.plan["archive_refs"]
        self.assertEqual(len(refs), 13)
        self.assertEqual(
            [item["disposition"] for item in refs].count("verify_existing"), 2
        )
        self.assertEqual(
            [item["disposition"] for item in refs].count("create_annotated"), 11
        )
        sources = [item["source"] for item in refs]
        tags = [item["tag"] for item in refs]
        self.assertEqual(len(sources), len(set(sources)))
        self.assertEqual(len(tags), len(set(tags)))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", item["tip"]) for item in refs))
        self.assertTrue(all(tag.startswith("refs/tags/archive/") for tag in tags))
        batches = self.plan["deletion_batches"]
        self.assertEqual([len(batch) for batch in batches], [4, 4, 4, 1])
        self.assertEqual([source for batch in batches for source in batch], sources)

def source13_budget_recipes():
    old = {'.github/workflows/project-tests.yml': '8920a91e79c8e25c34c0afdeda610d71a625dde9', '.github/workflows/parent-qualification.yml': '6d2d342e4b63d9e60602451157d13854bd52dde7', '.github/workflows/sync-validation.yml': '55d08b65a987224ce576459cede693cfd49375f6'}
    expected = {'.github/workflows/project-tests.yml': 'e1e009f489e2bd126d0546f75977dc73c6450dda', '.github/workflows/parent-qualification.yml': '2f4aec7f6463801a6deeb443b59977273197ea60', '.github/workflows/sync-validation.yml': 'cff76b696a4afd8658329a02ab33032672f292b9'}
    sync = zlib.decompress(base64.b85decode('c-rk5YjfMU@w<Kns`Ffun}T{+q#lhs&gIm^J;!!rJ8dU*H6RE|uql!TKsmZ3{q0=<ltk)bD{01;59coyfZfGn-@E()ohve80g_23C__mc&HjP{mPX0UED#A56No00G-8S&B{Hc1{w@(WVU*nA5sR51iYGB5!Guc*znn@;Caj0fXE8-n67j$QR74izjVEaD<445fG*i-{i4ZKZ+n+yIDoNa{pv8T|fXkF9I@X&g$FaW=DxmhzN5O70E?CghOtU{DHA~@UsRWNlpL2{!60ohHbewPst0dJFWe>d<ER(Pik|^>Cy}6o`NktO!i0yc3nnlr212U<0L}4FNMnUdFpGY>8WAdeVV@86n!J9BK+U>$h%0#YzqYy%KsR_8cqLmXX7OUlk76Z=3FyE~J6wN@3F`a25Bavh&+yUl-m*#>C=28@<wimdF#FRyt#~9Qy5==_VaHVpc_=dHd60>$=E%IHy2Tupi&5dJ`#QZmFx*8D7S7L2inV-cf!_AgcZ<!OtCoIVnp71zR4DM^XW}n5=xow`l>klsa!?$mahZp_xi{aq%<fK37p;{(IE#iLdR(Um_$F<u@1SEjr7#zzWgTti@8^<}nFUO4DAh>kllKHC=kwYQ`#tOXTil|YI0SJft!9Hy@nM(+DebTABou(U*w%2OZX`|C<w)cI~t@{o11Ddv-y3<$?yyI%zTdY7LEbO5P;c;OPymQ=}GgaJYLUO4v1q%W@;3NXxz>_3fdD(y&PEo|C44n-SH{fcvpjD8n{`>jGd4G8R`bDo8Mb;d~+Q$6v)$8HK>9740i!*{}Wxk`58y1)0UiV-8vYqzasmeHS`h!>ZFtqTfGS=DU@$qobe|rhWQ9@id@Lcv8SmLJw1<4e`EK5+zQx*~)70%wjN7cQ#psMKLzvw^j>$ppBc=fSW|GbB;u2!MvPu~rC@#x*ai?7Ww8n}C<(XM`4K>+*BNOZ9GbTmdJ<)|uHn#kJTtD}q8mp=oQv(xjVi_^isYFboqP$K?p_3EeBw+IX5Xv1){8lFFY4%_yY>NDWxpd_nx=I0c&`nOY9%5OUbYYUKECtMA;QYy%HL25%77&F8tlS~mmVmb&0HlCR~jOS{og7-agnD_!;upwmegu+S4AoXLYPc%UDYog0h4A?BzKv3OC76B(v<b;Ny)vynVotdmBImG0}bsSQl#oQK?c8xD@PJii_M57CmmB27K{oB!T87i+g%79-J2fz3D_E%ig@eFJ@-k;}|no1IIcbzOTo9Zk<S#6%$vDT!M&I;%lTb*H3*J2Dd4h(>Q<$>h%^5X3BqFTaOy3z6%#wGx9$h5O1_A(4r0isyjtcJVN1xDZC;$Q~`FIOy}Shed-tvaj)S`14VYwhIQ%UA;xwfyt_W#lMbdY#2wAwT0$V8sVTQWhy$Gj*1g5(}IUlgK=lGM;V+UzTOgwM^m_cRPoql%)mfof#!AT`BC@`o^)>I#w&viAc=QpAOKIh>ZxHVL!>hX@e)|)2CH0&`?1_vkCaLVdTk{&;}VYOR+VhLwHu3`gM;INS1CGhV53P+X*^etJ{Iyme=l3uR%<B^PGLBzBRmAf_SP!kS-6a`%a@-eMk@|pm~tk?<t8GSU7C9y4`lY-Ry!eSh(+Yx?Zcrn()tSxy%i8@bA+7j+KLZj~q0)f)tt$%i!;1N*)$Ks3XKU0Z)Q-_(YfT_dn|zs2=(r3q!x|vX<NOn{K`CdZ68I!}IE%A5bq0sULPdqh8l(-}5Z!IHASyGuu`wHpxV(;MLa^p516y*HVsD&@mR?Z632Fw|tEh)@#8mNT66!(4Iq4n4lNbv~IoLfWcdsJZOO;R&whOI6Qv|2Gha$LI(&aU?8PRglFjA1&RnkGowRX7BPIQbnHO4Dqu7sdSozVE~N4)HgOydJR9j?tF*|^)0+{7?l9yd=nVW(G%<iH*R2sRa{v#bH_Z)unz9mb&Bnus%s>lr)6pG|gXFHc#)pRsoGhNSvR8Qd9rNj!K+6{yV0huJa+jO#rpFe!0Umvc!z2orh`?ZVUWqh__Ylk)(E<jn)^|+KisXg^J){9YphD-1d+BP~ZQ5JtVdLRk4-b;Y;H4=Hg4kv{R%!Q=v9f}AqF}hOnMwdfX0mpsjl7r}mR75?JCC7O5h4-bE0}!%B}nvExo?d;;Kx6h|I%t)uTGfKB88vc9KtI>csayMz&V2gg$QT|WTJ%tW$hT20fP9WM^!-vC9loH%b~&lk%%5Hf~&>)BQKcNkJh4?velCvl??kQ?~VqiCvW;Ex@F9ZYOEt-Y0hB6n4C$fAWq#OFi4P<LsF2)BoR<)>S#{YFpEJQQ^=Yy{v1LY5wSd|7wEvSM@tR#qz`prMN%x1M9tSRQ+BSjUZLU%nu0L$nn|;W^;;x{%>wwQV>1J?bTk?0<qJ_4QjzZNFzn7V4z|M*=q49su_jf^hjqFVkVZ(3`k+?q<Q)?{oS|HgYt7HRXPldi$*wz^$-(Ys(*NgK|K&v=3fTTJ{5U$zyQYoA?J}PYe|f+4M>F-!nyJTWjm*UT(Hf(<-0{-Ps(b79`MY&fxx?BK^-}CI(<P({?~4yLpm9BwUZ0+Rv+(|ye*4Fq<O^K;p|tXyyZmEML%w&Xzl4vmBq)9@HFc2|yHMq_jYM~3CZ9e-KmLfGe*0m<vn_3RW;nz|C?3Mzq2H#i=aF{1$voflL*MPNpdL_Y!`=NRX|=mSyWQ!AcBD|hZ=_%(u=@Ege>yJ24Df;>55O;0H;K}{fZ8-*{#2^}Hz=oczA*XP2FRbZrgsO2W)8kAYcmP0ix%~6m8m;ytp?q&fr@(Qj)=H4Q`cWpwKM`yc@MQK{{ur>)>r'))
    step = '- name: Install selected artifact namespace utility\n  if: steps.{select}.outputs.requires_artifact_namespace == \'true\'\n  env:\n    FULL_HOST: ${{ steps.{select}.outputs.full_host }}\n  run: |\n    set -euo pipefail\n    if ! test -x /usr/bin/bwrap; then\n      if test "$FULL_HOST" != true; then\n        sudo apt-get -o Acquire::Retries=4 update\n      fi\n      sudo apt-get -o Acquire::Retries=4 install --no-install-recommends -y bubblewrap\n    fi\n    test -x /usr/bin/bwrap\n'
    result = {}
    for path, old_oid in old.items():
        raw = sync if path.endswith('sync-validation.yml') else (ROOT / 'tools/repository-checks/workflows/host' / Path(path).name).read_bytes()
        if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() != old_oid:
            raise AssertionError('historical source13 recipes must remain immutable')
        selected_sync = path.endswith('sync-validation.yml'); indent = 6 if selected_sync else 4
        marker = ' '*indent+'- name: '+('Prepare isolated shared and product Python validators' if selected_sync else 'Prepare isolated host evidence validators')+'\n'
        utility = ''.join(' '*indent+line+'\n' for line in step.replace('{select}', 'select' if selected_sync else 'host').splitlines())
        if raw.count(marker.encode()) != 1: raise AssertionError('source23 prerequisite position differs')
        raw = raw.replace(marker.encode(), (utility+marker).encode())
        if path.endswith('project-tests.yml'):
            if raw.count(b'    timeout-minutes: 20\n') != 1: raise AssertionError('source13 budget differs')
            raw = raw.replace(b'    timeout-minutes: 20\n', b'    timeout-minutes: 30\n')
        if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() != expected[path]:
            raise AssertionError('source23 recipe requires its exact reviewed bytes')
        result[path] = raw.decode('utf-8')
    return result


def source13_budget_recipe():
    return source13_budget_recipes()['.github/workflows/project-tests.yml']


def assert_reviewed_host_selection(case, source):
    """Accept the exact reviewed successor while retaining execution authority."""
    template = ROOT / 'tools/repository-checks/workflows/host/project-tests.yml'
    owned = ROOT / 'tools/repository-checks/workflows/android-owned/project-tests.yml'
    protected = ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests.yml'
    platform = protected.with_name('protected-project-tests-android-platform.yml')
    android_owned = source == owned.read_text(encoding='utf-8')
    platform_owner = source == platform.read_text(encoding='utf-8')
    protected_owner = source == protected.read_text(encoding='utf-8') or platform_owner
    budget_owner = source == source13_budget_recipe()
    if budget_owner:
        spec = importlib.util.spec_from_file_location(
            'budget_contract_packages', ROOT / 'tools/repository-checks/package_checks.py')
        packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
        row = next(row for row in packages.workflow_generations()
                   if row['name'] == 'npm-consumers-sync-ci-budget-v1')
        raw = source.encode()
        case.assertEqual(row['workflows']['.github/workflows/project-tests.yml'],
            {'mode':'100644','type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
        if source == WORKFLOW.read_text(encoding='utf-8'):
            case.assertEqual(reviewed_package_generation(), 'npm-consumers-sync-ci-budget-v1')
    elif android_owned or protected_owner:
        # Historical staged templates retain their exact approved identities
        # when a newer complete generation becomes the deployed workflow.
        spec = importlib.util.spec_from_file_location(
            'host_contract_packages', ROOT / 'tools/repository-checks/package_checks.py')
        packages = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packages)
        raw = source.encode()
        identity = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        matches = {row['name'] for row in packages.workflow_generations()
                   if row['workflows']['.github/workflows/project-tests.yml']['sha'] == identity}
        allowed = ({'protected-producer-original-default-v1'} if platform_owner else
                   set(PROTECTED_GENERATIONS) if protected_owner else {'android-owned-npm5-sync-ci-v1'})
        case.assertTrue(matches & allowed, 'host template requires an exact reviewed Git blob')
        if source == WORKFLOW.read_text(encoding='utf-8'):
            case.assertIn(reviewed_package_generation(), matches & allowed)
    else:
        case.assertEqual(source, template.read_text(encoding='utf-8'))
    jobs = workflow_data(source)['jobs']
    host = jobs['project-tests']
    case.assertEqual(host['if'], "needs.route.outputs.package_host_mode == 'full'")
    steps = host['steps']
    trusted = next(step for step in steps if 'checkout@' in step.get('uses', '')
                   and step['with'].get('path') == 'trusted')
    candidate = next(step for step in steps if 'checkout@' in step.get('uses', '')
                     and step['with'].get('path') == 'candidate')
    case.assertEqual(trusted['with']['ref'], '${{ github.event.repository.default_branch }}')
    case.assertEqual(candidate['with']['fetch-depth'], 2)
    for step in steps:
        if 'checkout@' in step.get('uses', ''):
            case.assertIs(step['with']['persist-credentials'], False)
    selection = next(step for step in steps if step.get('id') == 'host')
    execution = next(step for step in steps if step['name'] == 'Run independently selected host contracts')
    case.assertIn('--select-only --output "$GITHUB_OUTPUT"', selection['run'])
    controller = 'android_handoff.py' if android_owned else 'host_selection.py'
    if protected_owner:
        launcher = 'build/host-tests-env/bin/python -B trusted/tools/repository-checks/'
        case.assertIn(launcher + controller, execution['run'])
    else:
        case.assertIn('build/host-tests-env/bin/python trusted/tools/repository-checks/' + controller, execution['run'])
    for step in (selection, execution):
        case.assertIn('--candidate candidate', step['run'])
        if not android_owned:
            case.assertIn('--event "$GITHUB_EVENT_PATH" --sha "$GITHUB_SHA"', step['run'])
            case.assertIn('--expected-plan "$EXPECTED_PLAN"', step['run'])
        else:
            case.assertIn('trusted/tools/repository-checks/android_handoff.py', step['run'])
        case.assertEqual(step['env']['EXPECTED_PLAN'], '${{ needs.route.outputs.package_plan }}')
    if android_owned:
        controller_source = (ROOT / 'tools/repository-checks/android_handoff.py').read_text()
        controller_tree = ast.parse(controller_source)
        main = next(node for node in controller_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id in {'selected_host', 'project'}]
        case.assertEqual({node.func.id for node in calls}, {'selected_host', 'project'})
        for call in calls:
            case.assertEqual(ast.unparse(call.args[2]), "os.environ.get('GITHUB_SHA')")
            case.assertEqual(ast.unparse(call.args[3]), "os.environ.get('GITHUB_EVENT_NAME')")
            expected = next(item.value for item in call.keywords if item.arg == 'expected_plan')
            case.assertEqual(ast.unparse(expected), "os.environ.get('EXPECTED_PLAN')")
        case.assertIn('event = json.loads(Path(event_path).read_text())', controller_source)
        case.assertIn('event_path = os.environ.get("GITHUB_EVENT_PATH")', controller_source)
        case.assertIn('--receipt build/test-results/owned-project-execution.json', execution['run'])
    qt = next(step for step in steps if step['name'] == 'Install QML and portable C++ contract prerequisites')
    case.assertEqual(qt['if'], "steps.host.outputs.full_host == 'true'")
    if protected_owner:
        case.assertEqual(execution['if'], "steps.protected.outputs.protected_executed != 'true'")
        protected_step = next(step for step in steps
                              if step['name'] == 'Execute the selected protected shared owner')
        case.assertEqual(protected_step['if'], "needs.route.outputs.protected_full == 'true' && steps.protected-source.outputs.admitted == 'true'")
        case.assertIn('producer_workflow.py" shared', protected_step['run'])
        case.assertEqual(jobs['producer-publication']['name'],
                         'Publish final producer ${{ needs.project-tests.outputs.receipt_sha256 }}')
    runs = '\n'.join(step.get('run', '') for step in steps)
    case.assertIn('-r candidate/tests/requirements-host.txt', runs)
    case.assertNotIn('python candidate/tests/run-project-tests.py', runs)
    final = jobs['project-results']
    case.assertEqual(final['if'], 'always()')
    case.assertIn('project-tests', final['needs'])
    verify = final['steps'][-1]
    case.assertEqual(verify['env']['CHECK_RESULTS'], '${{ toJSON(needs) }}')
    if platform_owner:
        case.assertIn('platform-tests', final['needs'])
        case.assertEqual(jobs['platform-tests']['needs'], 'route')
        case.assertEqual(jobs['platform-tests']['if'], "needs.route.outputs.platform_required == 'true'")
        case.assertIn('trusted/tools/test-evidence/producer_workflow.py project-verify', verify['run'])
        case.assertIn('producer_workflow.py fallback-common', execution['run'])
        case.assertEqual(execution['env']['PLATFORM_REQUIRED'], '${{ needs.route.outputs.platform_required }}')
    else:
        case.assertIn('trusted/tools/repository-checks/package_checks.py verify', verify['run'])


class ProjectWorkflowContracts(unittest.TestCase):
    def test_issue_intake_has_one_required_central_pull_request_owner(self):
        issue = workflow_data((WORKFLOW_DIRECTORY / 'issue-intake.yml').read_text())
        self.assertEqual(set(issue.get('on', issue.get(True))),
                         {'issues', 'milestone', 'schedule', 'workflow_dispatch'})
        self.assertEqual(set(issue['jobs']), {'reconcile'})
        self.assertEqual(issue['permissions'], {'contents': 'read'})
        self.assertEqual(issue['jobs']['reconcile']['if'],
                         "github.repository == 'noah-l-frank/overte' && github.event_name != 'pull_request'")
        self.assertEqual(issue['jobs']['reconcile']['permissions'],
                         {'contents': 'read', 'issues': 'write'})
        registry = json.loads((ROOT / '.github/test-suites.json').read_text())
        owner = registry['suites']['issue-intake']
        self.assertEqual(owner['command'], ['python', 'tests/issue-intake-test.py'])
        self.assertEqual(owner['layer'], 'quick')
        ci37 = json.loads((ROOT / '.github/ci37-runtime.json').read_text())
        self.assertEqual(ci37['suites'].count('issue-intake'), 1)
        dependencies = json.loads((ROOT / '.github/test-suite-dependencies.json').read_text())
        self.assertEqual(dependencies['suites']['issue-intake']['kind'], 'repository')
        catalog = json.loads((ROOT / '.github/package-workflow-generations.json').read_text())
        generations = {row['name']: row['workflows'] for row in catalog['generations']}
        for generation, caller_path, project_path in (
                ('npm-consumers-sync-ci-v1', 'npm-consumers/repository-checks.yml', 'host/project-tests.yml'),
                ('protected-producer-original-default-v1', 'producers/repository-checks.yml',
                 'producers/protected-project-tests-android-platform.yml')):
            with self.subTest(generation=generation):
                recipes = {}
                for endpoint, relative in (('repository-checks', caller_path), ('project-tests', project_path)):
                    raw = (ROOT / 'tools/repository-checks/workflows' / relative).read_bytes()
                    self.assertEqual(generations[generation]['.github/workflows/' + endpoint + '.yml'],
                                     {'mode': '100644', 'type': 'blob',
                                      'sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()})
                    recipes[endpoint] = workflow_data(raw.decode())
                caller, project = recipes['repository-checks'], recipes['project-tests']
                events = caller.get('on', caller.get(True))
                self.assertIn('pull_request', events)
                self.assertNotIn('paths', events['pull_request'])
                self.assertNotIn('paths-ignore', events['pull_request'])
                route = caller['jobs']['project']
                self.assertEqual(route['uses'], './.github/workflows/project-tests.yml')
                self.assertIn("needs.route.outputs.package_host_mode == 'full'", route['if'])
                self.assertIn('project', caller['jobs']['repository-checks']['needs'])
                self.assertIn('always()', caller['jobs']['repository-checks']['if'])
                host = project['jobs']['project-tests']
                self.assertEqual(host['if'], "needs.route.outputs.package_host_mode == 'full'")
                execution = next(step for step in host['steps']
                                 if step.get('name') == 'Run independently selected host contracts')
                self.assertIn('trusted/tools/repository-checks/host_selection.py', execution['run'])
                self.assertIn('--expected-plan "$EXPECTED_PLAN"', execution['run'])
                final = project['jobs']['project-results']
                self.assertEqual(final['if'], 'always()')
                self.assertIn('project-tests', final['needs'])

    def test_prospective_seven_target_recipes_require_the_complete_canonical_generation(self):
        spec = importlib.util.spec_from_file_location(
            'prospective_workflow_contract_packages', ROOT / 'tools/repository-checks/package_checks.py')
        packages = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packages)
        packages, tree = prospective_package_tree()
        generation = packages.validate_tree_wiring(tree)
        self.assertEqual(generation, 'protected-producer-original-default-v1')
        historical = next(row for row in packages.workflow_generations()
                          if row['name'] == 'protected-producer-seven-target-ci-v1')
        self.assertEqual(packages.validate_tree_wiring(historical['workflows']), historical['name'])
        project = (ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests.yml').read_text()
        caller = (ROOT / 'tools/repository-checks/workflows/producers/repository-checks.yml').read_text()
        # Preserve the exact historical21 host-template contract separately.
        raw = project.encode()
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                         historical['workflows']['.github/workflows/project-tests.yml']['sha'])
        with mock.patch.object(sys.modules[__name__], 'reviewed_package_generation', return_value=historical['name']):
            assert_reviewed_host_selection(self, project)
        # Installation22 is admitted only after all actual future endpoint bytes
        # match the complete catalog, including separate mandatory platform work.
        future = workflow_data((ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml').read_text())
        self.assertIn('platform-tests', future['jobs'])
        self.assertIn('platform-tests', future['jobs']['project-results']['needs'])
        with mock.patch.object(sys.modules[__name__], 'reviewed_package_generation', return_value=generation):
            self.assertEqual(assert_project_caller_routing(self, caller), 'package_host_mode')
            with self.assertRaises(AssertionError):
                assert_project_caller_routing(self, caller + '\n# unreviewed caller\n')
        # Strict source identity needs separate non-root sibling checkouts.
        from pathlib import PurePosixPath
        import shlex
        caller_workflow = workflow_data(caller)
        verifier = caller_workflow['jobs']['repository-checks']
        trusted = next(step for step in verifier['steps']
                       if step.get('name') == 'Check out trusted result verifier')
        candidate = next(step for step in verifier['steps']
                         if step.get('name') == 'Check out the exact candidate without credentials')
        verify = next(step for step in verifier['steps']
                      if step.get('name') == 'Require all selected checks to succeed')
        paths = []
        for checkout in (trusted, candidate):
            raw_path = checkout['with'].get('path', '.')
            self.assertIsInstance(raw_path, str)
            self.assertTrue(raw_path)
            path = PurePosixPath(raw_path)
            self.assertFalse(path.is_absolute())
            self.assertNotEqual(path, PurePosixPath('.'))
            self.assertNotIn('..', path.parts)
            paths.append(path)
        trusted_path, candidate_path = paths
        self.assertNotEqual(trusted_path, candidate_path)
        self.assertNotIn(trusted_path, candidate_path.parents)
        self.assertNotIn(candidate_path, trusted_path.parents)
        self.assertEqual(trusted['with']['ref'], '${{ github.event.repository.default_branch }}')
        self.assertIs(trusted['with']['persist-credentials'], False)
        self.assertEqual(candidate['with']['fetch-depth'], 2)
        self.assertIs(candidate['with']['persist-credentials'], False)
        command = shlex.split(verify['run'])
        self.assertEqual(command[0], 'python3')
        self.assertEqual(PurePosixPath(command[1]), trusted_path / 'tools/repository-checks/check.py')
        self.assertEqual(command[2], 'verify')
        self.assertEqual(command.count('--candidate'), 1)
        candidate_index = command.index('--candidate') + 1
        self.assertLess(candidate_index, len(command))
        self.assertEqual(PurePosixPath(command[candidate_index]), candidate_path)
        self.assertNotIn('working-directory', verify)
        self.assertNotIn('working-directory', verifier.get('defaults', {}).get('run', {}))
        self.assertNotIn('working-directory', caller_workflow.get('defaults', {}).get('run', {}))

    def test_security_deferral_keeps_every_other_security_check_selected(self):
        workflow = workflow_data((WORKFLOW_DIRECTORY / 'workflow-security.yml').read_text())
        self.assertEqual(workflow_events((WORKFLOW_DIRECTORY / 'workflow-security.yml').read_text())['workflow_call'],
            {'inputs': {'defer_workflow_contracts': {'type': 'boolean', 'default': False,
                'description': 'Exact caller verifies contracts after the shared owner; this input grants no test authority'}}})
        steps = workflow['jobs']['static-analysis']['steps']
        self.assertNotIn('if', workflow['jobs']['static-analysis'])
        for name, command in (('Verify immutable action references', 'python3 tools/workflow-security/check-action-pins.py'),
                ('Lint workflow syntax and runner labels', 'actionlint -config-file .github/actionlint.yaml -no-color'),
                ('Audit workflow security', 'zizmor --min-severity medium .github/workflows'),
                ('Scan workflow files for secrets with redacted output', 'gitleaks dir --redact=100 --no-banner --no-color .github')):
            step = next(step for step in steps if step['name'] == name)
            self.assertEqual(step['run'], command)
            self.assertNotIn('defer_workflow_contracts', step.get('if', ''))
        contract = next(step for step in steps if step['name'] == 'Verify fail-closed workflow contracts')
        self.assertEqual(contract['if'], 'always() && inputs.defer_workflow_contracts != true')
        self.assertEqual(contract['run'], 'PYTHONDONTWRITEBYTECODE=1 python3 tests/workflow-contract-test.py')

    def test_reviewed_host_selection_rejects_foreign_workflow_bytes(self):
        for relative in ('host/project-tests.yml', 'android-owned/project-tests.yml',
                         'producers/protected-project-tests.yml',
                         'producers/protected-project-tests-android-platform.yml'):
            source = (ROOT / 'tools/repository-checks/workflows' / relative).read_text()
            with self.subTest(relative=relative), self.assertRaises(AssertionError):
                assert_reviewed_host_selection(self, source + '\n# foreign workflow bytes\n')

    def test_reviewed_host_selection_requires_the_complete_installed_generation(self):
        source = WORKFLOW.read_text()
        if source == (ROOT / 'tools/repository-checks/workflows/host/project-tests.yml').read_text():
            return  # This historical pre-generation template retains its original contract.
        with mock.patch.object(sys.modules[__name__], 'reviewed_package_generation',
                               return_value='unknown-or-mixed-generation'):
            with self.assertRaises(AssertionError):
                assert_reviewed_host_selection(self, source)

    def test_codeql_recipe_rejects_unreviewed_local_workflow_bytes(self):
        source = (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml').read_text()
        with self.assertRaises(AssertionError):
            codeql_generation(self, source + '\n# foreign reusable recipe\n')

    def test_tool_dependency_lane_is_bounded_and_selected_by_the_trusted_router(self):
        jobs = workflow_data(WORKFLOW.read_text())['jobs']
        self.assertEqual(jobs['project-tests']['if'], "needs.route.outputs.package_host_mode == 'full'")
        light = jobs['tool-dependencies']
        self.assertEqual(light['if'], "needs.route.outputs.package_host_mode == 'tool-dependencies'")
        runs = '\n'.join(step.get('run', '') for step in light['steps'])
        self.assertIn('trusted/tools/repository-checks/package_checks.py run', runs)
        self.assertIn('--lane tool-dependencies', runs)
        self.assertNotIn('apt-get', runs)
        self.assertNotIn('tests/run-project-tests.py', runs)
        for step in light['steps']:
            if step.get('uses', '').startswith('actions/checkout@'):
                self.assertIs(step['with']['persist-credentials'], False)
        self.assertEqual(light['steps'][0]['with']['path'], 'trusted')
        self.assertEqual(light['steps'][0]['with']['ref'], '${{ github.event.repository.default_branch }}')
        controller = (ROOT / 'tools/repository-checks/package_checks.py').read_text()
        self.assertIn('with controller.candidate_process_environment():', controller)
        final = jobs['project-results']
        self.assertEqual(final['if'], 'always()')
        expected_needs = {'route', 'project-tests', 'tool-dependencies', 'package-checks'}
        if reviewed_package_generation() == 'protected-producer-original-default-v1':
            expected_needs.add('platform-tests')
        self.assertEqual(set(final['needs']), expected_needs)
        aggregate = (WORKFLOW_DIRECTORY / 'repository-checks.yml').read_text()
        mode = assert_project_caller_routing(self, aggregate)
        caller = workflow_data(aggregate)['jobs']['project']
        self.assertIn("needs.route.outputs." + mode + " == 'tool-dependencies'", caller['if'])
        self.assertIn("needs.route.outputs.package_set != '[]'", caller['if'])
        self.assertEqual(caller['with']['dependency_projects'], '${{ needs.route.outputs.tool_projects }}')
        self.assertEqual(caller['with']['expected_package_plan'], '${{ needs.route.outputs.package_plan }}')

    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_untrusted_pull_requests_have_read_only_permissions(self):
        self.assertIn("workflow_call:", self.source)
        caller = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text()
        self.assertIn("pull_request:", caller)
        self.assertNotIn("pull_request_target:", caller)
        self.assertNotRegex(caller, r"(?m)^\s+[a-z-]+: write$")
        self.assertNotIn("pull_request_target:", self.source)
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        self.assertNotRegex(self.source, r"(?m)^\s*(id-token|packages|actions): write$")

    def test_every_action_is_pinned_to_a_full_commit(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 5)
        self.assertEqual(
            [action for action in actions if not FULL_SHA_ACTION.fullmatch(action)],
            [],
            "pin every action to an immutable 40-character commit SHA",
        )

    def test_checkout_does_not_persist_credentials(self):
        self.assertIn("persist-credentials: false", self.source)

    def test_duplicate_runs_are_cancelled_and_jobs_are_bounded(self):
        self.assertIn("cancel-in-progress: true", self.source)
        timeout = re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)\s*$", self.source)
        self.assertIsNotNone(timeout)
        self.assertLessEqual(int(timeout.group(1)), 30)

    def test_reports_have_short_explicit_retention(self):
        retention = re.search(r"(?m)^\s+retention-days:\s*(\d+)\s*$", self.source)
        self.assertIsNotNone(retention)
        self.assertLessEqual(int(retention.group(1)), 7)
        self.assertNotIn("*.apk", self.source.lower())

    def test_ci_uses_the_repository_entry_point(self):
        self.assertIn("tests/run-project-tests.py", self.source)
        self.assertIn("--junit build/test-results/project-tests.xml", self.source)

    def test_ci_runs_complete_device_control_plane_with_qml(self):
        self.assertIn("qml-module-qttest", self.source)
        self.assertIn("qtdeclarative5-dev-tools", self.source)
        if any('trusted/tools/repository-checks/' + name in self.source
               for name in ('host_selection.py', 'android_handoff.py')):
            assert_reviewed_host_selection(self, self.source)
        else:
            self.assertIn("--profile host --timeout 240 --host-timeout 900", self.source)
        self.assertIn("device-e2e-control-plane.xml", self.source)

    def test_budget_source_recipe_keeps_commands_and_rejects_other_budget_or_setup_changes(self):
        recipes = source13_budget_recipes()
        source = recipes['.github/workflows/project-tests.yml']
        assert_reviewed_host_selection(self, source)
        spec = importlib.util.spec_from_file_location('namespace_contract_packages', ROOT / 'tools/repository-checks/package_checks.py')
        packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
        budget = next(row for row in packages.workflow_generations() if row['name']=='npm-consumers-sync-ci-budget-v1')
        for path, recipe in recipes.items():
            with self.subTest(path=path):
                raw = recipe.encode()
                self.assertEqual(budget['workflows'][path], {'mode':'100644','type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
                jobs = workflow_data(recipe)['jobs']
                job = jobs['validate' if path.endswith('sync-validation.yml') else 'qualify-parent' if path.endswith('parent-qualification.yml') else 'project-tests']
                steps = job['steps']; utility = next(step for step in steps if step['name']=='Install selected artifact namespace utility')
                select = 'select' if path.endswith('sync-validation.yml') else 'host'
                self.assertEqual(utility['if'], "steps."+select+".outputs.requires_artifact_namespace == 'true'")
                self.assertEqual(utility['run'], 'set -euo pipefail\nif ! test -x /usr/bin/bwrap; then\n  if test "$FULL_HOST" != true; then\n    sudo apt-get -o Acquire::Retries=4 update\n  fi\n  sudo apt-get -o Acquire::Retries=4 install --no-install-recommends -y bubblewrap\nfi\ntest -x /usr/bin/bwrap\n')
                self.assertNotIn('full_host', utility['if'])
                self.assertEqual(utility['env'], {'FULL_HOST':'${{ steps.'+select+'.outputs.full_host }}'})
                self.assertIn('if test "$FULL_HOST" != true; then', utility['run'])
                self.assertNotIn('qml', utility['run'])
                self.assertEqual(sum(step['name']=='Install selected artifact namespace utility' for step in steps), 1)
                qt = next(step for step in steps if step['name'] == ('Install candidate host prerequisites' if select=='select' else 'Install QML and portable C++ contract prerequisites'))
                self.assertEqual(qt['if'], "steps."+select+".outputs.full_host == 'true'")
                self.assertLess(steps.index(qt), steps.index(utility))
        jobs = workflow_data(source)['jobs']
        self.assertEqual(jobs['project-tests']['timeout-minutes'], 30)
        old = workflow_data((ROOT / 'tools/repository-checks/workflows/host/project-tests.yml').read_text())
        old['jobs']['project-tests']['timeout-minutes'] = 30
        jobs['project-tests']['steps'].remove(next(step for step in jobs['project-tests']['steps'] if step['name']=='Install selected artifact namespace utility'))
        self.assertEqual(jobs, old['jobs'])
        for changed in (source.replace('timeout-minutes: 30','timeout-minutes: 31'),
                        source.replace('requires_artifact_namespace', 'full_host'),
                        source.replace('-y bubblewrap', '-y bubblewrap curl'),
                        source.replace('host_selection.py','foreign_selection.py')):
            with self.subTest(changed=changed[:100]), self.assertRaises(AssertionError):
                assert_reviewed_host_selection(self, changed)
        with mock.patch.object(sys.modules[__name__], 'WORKFLOW') as current, \
             mock.patch.object(sys.modules[__name__], 'reviewed_package_generation',return_value='unknown-or-mixed-generation'):
            current.read_text.return_value = source
            with self.assertRaises(AssertionError): assert_reviewed_host_selection(self, source)


class HostWorkflowRoutingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            "shared": WORKFLOW.read_text(encoding="utf-8"),
            "parent": PARENT_QUALIFICATION_WORKFLOW.read_text(encoding="utf-8"),
        }
        cls.branches = json.loads((ROOT / ".github/branch-policy.json").read_text())["branches"]

    def selected(self, branch, changed_paths):
        return [name for name, source in self.workflows.items()
                if selects_host_push(source, branch, changed_paths)]

    def test_every_permanent_branch_push_runs_exactly_one_complete_host_lane(self):
        for branch, settings in self.branches.items():
            with self.subTest(branch=branch):
                expected = "parent" if settings["children"] else "shared"
                self.assertEqual(self.selected(branch, ["interface/src/Application.cpp"]), [expected])

    def test_development_push_coverage_and_manual_reusable_entrypoints_remain(self):
        for branch in ("ci/main/workflow-change", "test/main/test-change", "ci/example", "test/example"):
            with self.subTest(branch=branch):
                self.assertEqual(self.selected(branch, ["tests/new-test.py"]), ["shared"])
        for branch in ("feature/main/example", "ci", "testing/example"):
            self.assertEqual(self.selected(branch, ["tests/new-test.py"]), [])
        for event in ("workflow_call", "workflow_dispatch"):
            self.assertIn(event, workflow_events(self.workflows['shared']))
            self.assertNotIn(event, workflow_events(self.workflows['parent']))
        aggregate = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text()
        self.assertIn("pull_request:", aggregate)
        assert_project_caller_routing(self, aggregate)
        self.assertIn("uses: ./.github/workflows/project-tests.yml", aggregate)

    def test_only_markdown_changes_skip_push_lanes(self):
        for branch in (*self.branches, "ci/main/example", "test/main/example"):
            with self.subTest(branch=branch):
                self.assertEqual(self.selected(branch, ["README.md", "docs/guide.md"]), [])
                self.assertEqual(len(self.selected(branch, ["README.md", "tests/new-test.py"])), 1)
                self.assertEqual(len(self.selected(branch, ["unknown.extension"])), 1)

    def test_routing_parser_rejects_unsupported_or_incomplete_configuration(self):
        valid = 'on:\n  push:\n    branches: [main]\n    paths-ignore:\n      - "**/*.md"\n'
        self.assertTrue(selects_host_push(valid, "main", ["tests/test.py"]))
        variants = (
            valid.replace("branches: [main]", "branches-ignore: [main]"),
            valid.replace("branches: [main]", "branches: []"),
            valid.replace("branches: [main]", "branches: [main, '!apple-main']"),
            valid.replace('"**/*.md"', '"**/*.py"'),
            valid.replace("    branches: [main]\n", ""),
            valid.replace("  push:\n", "  push: {}\n"),
            valid + "    tags: [v*]\n",
        )
        for source in variants:
            with self.subTest(source=source), self.assertRaises(ValueError):
                push_filters(source)

    def test_parent_and_shared_keep_matching_tools_and_complete_host_coverage(self):
        for name, source in self.workflows.items():
            with self.subTest(workflow=name):
                workflow = workflow_data(source)
                steps = [step for job in workflow['jobs'].values() for step in job.get('steps', [])]
                for action, key, version in (('setup-python', 'python-version', '3.12'),
                                             ('setup-node', 'node-version', '22'),
                                             ('setup-java', 'java-version', '17')):
                    matching = [step['with'] for step in steps if step.get('uses', '').startswith('actions/' + action + '@')]
                    self.assertTrue(any(item.get(key) == version for item in matching), action)
                    if action == 'setup-java': self.assertTrue(all(item['distribution'] == 'temurin' for item in matching))
                runs = '\n'.join(step.get('run', '') for step in steps)
                for fragment in ("command -v cmake", "command -v ctest",
                                 "qml-module-qttest", "qtdeclarative5-dev-tools",
                                 "qt6-base-dev qt6-base-dev-tools",
                                 "unshare --user --map-root-user --net true"):
                    self.assertIn(fragment, runs)
                if name == "parent":
                    self.assertIn("-r trusted/tests/requirements-host.txt", runs)
                    self.assertIn("build/host-tests-env/bin/python trusted/tools/test-evidence/run.py", runs)
                    self.assertIn("--candidate candidate --include-platform --timeout 240 --host-timeout 900", runs)
                    self.assertNotIn("python tests/run-project-tests.py", source)
                    self.assertNotIn("candidate/tests/run-project-tests.py", source)
                elif any('trusted/tools/repository-checks/' + controller in source
                         for controller in ('host_selection.py', 'android_handoff.py')):
                    assert_reviewed_host_selection(self, source)
                else:
                    self.assertIn("-r tests/requirements-host.txt", runs)
                    self.assertEqual(runs.count("tests/run-project-tests.py"), 1)
                    self.assertIn("build/host-tests-env/bin/python tests/run-project-tests.py", runs)
                    self.assertIn("--profile host --timeout 240 --host-timeout 900", runs)
                self.assertNotIn("tests/device/run_control_plane_tests.py", source)
                self.assertNotIn("--shared-only", source)
                self.assertNotIn("--platform-only", source)
                self.assertNotIn("continue-on-error:", source)

    def test_host_namespace_setup_is_ephemeral_and_preserves_isolation(self):
        import yaml
        workflows = [(name, source, "Prepare isolated host evidence validators")
                     for name, source in self.workflows.items()]
        workflows.append(("sync-fallback", SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8"),
                          "Prepare isolated shared and product Python validators"))
        for name, source, step in workflows:
            with self.subTest(workflow=name):
                self.assertIn("runs-on: ubuntu-24.04", source)
                setup_steps = [item for job in yaml.safe_load(source)['jobs'].values()
                               for item in job.get('steps', []) if item.get('name') == step]
                self.assertEqual(len(setup_steps), 1)
                setup = setup_steps[0]['run']
                guard = 'test "$RUNNER_ENVIRONMENT" = github-hosted'
                setting = "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0"
                probe = "unshare --user --map-root-user --net true"
                self.assertLess(setup.index(guard), setup.index(setting))
                self.assertLess(setup.index(setting), setup.index(probe))
                self.assertLess(setup.index(probe), setup.index("python3 -m venv"))
                self.assertNotIn("||", setup)
                self.assertNotIn("/etc/sysctl", setup)
                self.assertNotIn("sudo unshare", source)
                self.assertNotIn("sudo python", source)
                self.assertNotIn("continue-on-error:", source)

    def test_sync_platform_and_fallback_install_host_packages_before_execution(self):
        import yaml
        workflow = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())
        steps = workflow['jobs']['validate']['steps']
        installs = [(index, step) for index, step in enumerate(steps)
                    if 'apt-get' in step.get('run', '') and 'install' in step['run']]
        self.assertEqual(len(installs), 1, 'Both paths must share one prerequisite installation')
        index, install = installs[0]
        self.assertEqual(install['if'], sync_condition(
            "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')", "steps.select.outputs.full_host == 'true'", setup=True))
        for package in ('qt6-base-dev', 'qt6-base-dev-tools', 'pkg-config',
                        'qml-module-qttest', 'qtdeclarative5-dev-tools'):
            self.assertIn(package, install['run'].split())
        executions = [i for i, step in enumerate(steps)
                      if step.get('name') == 'Verify exact candidate suites and complete runtime identity']
        self.assertEqual(len(executions), 1, 'Reuse and fallback share one trusted execution controller')
        self.assertLess(index, executions[0])
        self.assertEqual(steps[executions[0]]['if'], sync_condition(
            "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')", "steps.select.outputs.lane != 'legacy-bounded'"))

    def test_reused_product_suites_share_the_prepared_python_interpreter(self):
        import yaml
        steps = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        name = 'Prepare isolated shared and product Python validators'
        index = next(i for i, step in enumerate(steps) if step.get('name') == name)
        prepare = steps[index]
        product = next(step for step in steps if step.get('name') == 'Verify exact candidate suites and complete runtime identity')
        expected_prepare = sync_condition(
            "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')",
            "steps.select.outputs.lane != 'legacy-bounded'", setup=True)
        self.assertEqual(prepare['if'], expected_prepare)
        self.assertIsNone(prepare.get('working-directory'))
        self.assertIsNone(product.get('working-directory'))
        self.assertLess(index, steps.index(product))
        interpreter = 'build/host-tests-env/bin/python'
        self.assertIn('python3 -m venv build/host-tests-env', prepare['run'])
        self.assertIn(interpreter + ' -m pip install --disable-pip-version-check '
                      '-r trusted/tests/requirements-host.txt', prepare['run'])
        if 'SYNC_VALIDATOR_PYTHON' in product['env']:
            self.assertEqual(product['run'].split()[:2], ['"$SYNC_VALIDATOR_PYTHON"', '-B'])
            self.assertEqual(product['env']['SYNC_VALIDATOR_PYTHON'],
                "${{ steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.native_setup != '' && 'python3' || 'build/host-tests-env/bin/python' }}")
            self.assertEqual(product['env']['EXPECTED_NATIVE_SETUP'], '${{ steps.select.outputs.native_setup }}')
            self.assertIn('--expected-native-setup "$EXPECTED_NATIVE_SETUP"', product['run'])
        else:
            self.assertEqual(product['run'].split()[0], interpreter)
        self.assertIn('trusted/tools/test-evidence/validate-sync.py', product['run'])
        self.assertIn('--candidate candidate', product['run'])
        self.assertEqual(prepare['env'], {'GH_TOKEN': '', 'GITHUB_TOKEN': ''})
        # The controller uses this read-only token for API evidence; its scoped
        # candidate environment removes it before executing any candidate input.
        self.assertEqual(product['env']['GH_TOKEN'], '${{ github.token }}')
        self.assertNotIn('continue-on-error', prepare)
        self.assertNotIn('continue-on-error', product)

    def test_complete_fallback_isolates_disposable_git_background_writers(self):
        import yaml
        steps = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        fallback = next(step for step in steps if step.get('name') == 'Verify exact candidate suites and complete runtime identity')
        self.assertEqual(fallback['if'], sync_condition(
            "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')", "steps.select.outputs.lane != 'legacy-bounded'"))
        self.assertNotEqual(fallback.get('working-directory'), 'candidate')
        self.assertNotIn('git config --global', fallback['run'])
        self.assertNotIn('continue-on-error', fallback)
        # Background-writer policy now belongs to the shared trusted controller,
        # applying equally to qualification, reuse, and fallback subprocesses.
        directory = ROOT / 'tools/test-evidence'
        spec = importlib.util.spec_from_file_location('workflow_contract_execution', directory / 'execution.py')
        execution = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, 'path', [str(directory), *sys.path]), mock.patch.dict(sys.modules):
            spec.loader.exec_module(execution)
            hostile = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'maintenance.auto',
                       'GIT_CONFIG_VALUE_0': 'true', 'GIT_CONFIG_KEY_9': 'gc.auto', 'GIT_CONFIG_VALUE_9': '1',
                       'GH_TOKEN': 'fixture-private', 'GITHUB_TOKEN': 'fixture-private',
                       'GITHUB_ENV': '/fixture/private-command-file', 'GITHUB_OUTPUT': '/fixture/private-command-file'}
            with mock.patch.dict(os.environ, hostile):
                before = dict(os.environ)
                with execution.candidate_process_environment():
                    self.assertEqual(os.environ['GIT_CONFIG_COUNT'], '2')
                    self.assertNotIn('GIT_CONFIG_KEY_9', os.environ)
                    for variable in ('GH_TOKEN', 'GITHUB_TOKEN', 'GITHUB_ENV', 'GITHUB_OUTPUT'):
                        self.assertNotIn(variable, os.environ)
                    for key, expected in (('maintenance.auto', 'false'), ('gc.auto', '0')):
                        observed = subprocess.check_output(['git', 'config', '--get', key], text=True).strip()
                        self.assertEqual(observed, expected)
                self.assertEqual(dict(os.environ), before, 'Trusted API/runtime operations retain their original environment')

    def test_parent_evidence_stays_bound_to_the_successful_exact_push(self):
        source = self.workflows["parent"]
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn("PARENT_COMMIT: ${{ github.sha }}", source)
        self.assertIn("RUN_ATTEMPT: ${{ github.run_attempt }}", source)
        self.assertIn("RUN_ID: ${{ github.run_id }}", source)

        self.assertIn("cancel-in-progress: false", source)
        self.assertLess(source.index("trusted/tools/test-evidence/run.py"), source.index("qualification.py"))
        self.assertIn('trusted/tools/sync-test-reuse/qualification.py', source)
        self.assertIn('--execution-receipt build/parent-qualification/execution.json', source)
        self.assertIn('--receipt build/parent-qualification/execution.json', source)
        self.assertIn('--candidate candidate', source)
        jobs = workflow_data(source)['jobs']
        platform = (ROOT / 'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml').read_text()
        platform_owner = source == platform
        if platform_owner:
            self.assertEqual(reviewed_package_generation(), 'protected-producer-original-default-v1')
            self.assertEqual(set(jobs['qualify-parent']['needs']), {'route', 'common-parent', 'platform-tests'})
            self.assertIn('producer_workflow.py parent-verify', jobs['qualify-parent']['steps'][-1]['run'])
        steps = jobs['common-parent' if platform_owner else 'qualify-parent']['steps']
        create = next(step for step in steps if step['name'] == 'Create content-addressed qualification evidence')
        upload = next(step for step in steps if step['name'] == 'Upload immutable qualification evidence')
        canonical = (ROOT / 'tools/repository-checks/workflows/host/parent-qualification.yml').read_text()
        protected = (ROOT / 'tools/repository-checks/workflows/producers/parent-qualification.yml').read_text()
        if source in (canonical, protected, platform):
            protected_owner = source == protected or platform_owner
            if protected_owner:
                self.assertIn(reviewed_package_generation(), METADATA_PRODUCER_GENERATIONS)
            expected = "steps.host.outputs.complete_receipt == 'true'"
            if protected_owner:
                expected = "steps.reuse.outputs.shared_reused != 'true' && (" + expected + ")"
            if platform_owner:
                expected = "needs.route.outputs.platform_required != 'true' && (" + expected + ")"
            selected = next(step for step in steps if step.get('id') == 'host')
            route = next(step for step in steps if step['name'] == 'Require a complete host execution route')
            qt = next(step for step in steps if step['name'] == 'Install QML and portable C++ contract prerequisites')
            self.assertLess(steps.index(selected), steps.index(route))
            self.assertLess(steps.index(route), steps.index(qt))
            self.assertEqual(qt['if'], ("steps.reuse.outputs.shared_reused != 'true' && (steps.host.outputs.full_host == 'true')"
                                      if protected_owner else "steps.host.outputs.full_host == 'true'"))
            partial = next(step for step in steps if step['name'] == 'Run independently selected parent host contracts')
            self.assertIn("steps.host.outputs.complete_receipt == 'false'", partial['if'])
            self.assertIn('trusted/tools/repository-checks/host_selection.py', partial['run'])
            self.assertNotIn('--receipt', partial['run'])
            self.assertNotIn('qualification.py', partial['run'])
        else:
            self.assertEqual(source, (ROOT / 'tools/repository-checks/workflows/packages/parent-qualification.yml').read_text())
            expected = "steps.route.outputs.package_host_mode == 'full'"
        for step in (create, upload):
            self.assertEqual(step['if'], expected)
        self.assertIn('Check only affected tool dependencies and behavior', source)
        self.assertNotIn('continue-on-error:', source)
        self.assertEqual(upload['with']['name'], 'parent-qualification-${{ github.sha }}')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')

    def test_parent_trusted_checkout_contains_transitive_host_requirements(self):
        import yaml
        workflow = yaml.safe_load(PARENT_QUALIFICATION_WORKFLOW.read_text())
        checkout = next(step['with'] for step in workflow['jobs']['qualify-parent']['steps']
                        if step.get('with', {}).get('path') == 'trusted')
        # File paths require non-cone mode. Every recursively included pip file
        # must exist in this checkout before installation/runtime fingerprinting.
        self.assertIs(checkout['sparse-checkout-cone-mode'], False)
        included = checkout['sparse-checkout'].split()
        pending = [ROOT / 'tests/requirements-host.txt']
        seen = set()
        while pending:
            path = pending.pop().resolve()
            if path in seen:
                continue
            seen.add(path)
            relative = path.relative_to(ROOT).as_posix()
            self.assertTrue(any(relative == entry or relative.startswith(entry.rstrip('/') + '/')
                                for entry in included), relative + ' is missing from trusted checkout')
            for line in path.read_text().splitlines():
                if line.strip().startswith('-r '):
                    pending.append(path.parent / line.strip()[3:].strip())

    def test_bounded_tool_sync_skips_product_and_host_prerequisites(self):
        import yaml
        steps = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        tools = next(step for step in steps if step['name'] == 'Verify bounded synchronization without product setup')
        self.assertEqual(tools['if'], sync_condition(
            "inputs.mode == 'reuse' && (inputs.profile == 'documentation' || inputs.profile == 'tool-dependencies')",
            "steps.select.outputs.lane == 'legacy-bounded'"))
        self.assertEqual(tools['run'].split()[0], 'python3')
        self.assertIn('trusted/tools/test-evidence/validate-sync.py', tools['run'])
        self.assertIn('--mode reuse --profile "$PROFILE"', tools['run'])
        self.assertNotIn('apt-get', tools['run'])
        self.assertNotIn('host-tests-env', tools['run'])
        product = next(step for step in steps if step.get('name') == 'Verify exact candidate suites and complete runtime identity')
        self.assertEqual(product['if'], sync_condition(
            "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')", "steps.select.outputs.lane != 'legacy-bounded'"))
        for step in steps:
            if 'apt-get' in step.get('run', '') or step.get('name') == 'Set up candidate Java':
                self.assertEqual(step['if'], sync_condition(
                    "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')", "steps.select.outputs.full_host == 'true'", setup=True))
            elif step.get('name') == 'Prepare isolated shared and product Python validators':
                self.assertEqual(step['if'], sync_condition(
                    "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')",
                    "steps.select.outputs.lane != 'legacy-bounded'", setup=True))






class SharedReleaseBundleWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RELEASE_BUNDLE_WORKFLOW.read_text(encoding="utf-8")

    def test_reusable_gate_has_no_untrusted_or_manual_entrypoint(self):
        self.assertRegex(self.source, r"(?m)^  workflow_call:$")
        self.assertNotRegex(
            self.source,
            r"(?m)^  (pull_request|pull_request_target|push|workflow_dispatch):$",
        )
        self.assertIn("validate-release-bundle.py", self.source)
        self.assertIn('git rev-list -n 1 "refs/tags/$RELEASE_TAG"', self.source)
        self.assertEqual(self.source.count('[[ "$GITHUB_REF_TYPE" == tag ]]'), 2)
        self.assertEqual(
            self.source.count('[[ "$GITHUB_REF" == "refs/tags/$RELEASE_TAG" ]]'), 2
        )

    def test_release_products_tags_and_publish_environments_are_closed_sets(self):
        for value in (
                "android-phone-release-candidate", "pico4-release-candidate",
                "^android-phone-v[0-9]+\\.[0-9]+\\.[0-9]+-alpha\\.[0-9]+$",
                "^pico4-v[0-9]+\\.[0-9]+\\.[0-9]+-rc\\.[0-9]+$"):
            self.assertIn(value, self.source)
        self.assertEqual(self.source.count("Unsupported release product"), 2)
        publish = self.source.split("  draft-publish:", 1)[1]
        self.assertLess(
            publish.index("Reject non-tag or unprotected release invocation"),
            publish.index("actions/checkout@"),
        )

    def test_build_and_sbom_attestations_are_isolated_and_pinned(self):
        attest = self.source.split("  attest:", 1)[1].split("  draft-publish:", 1)[0]
        self.assertRegex(
            attest,
            r"(?m)^    permissions:\n      contents: read\n      id-token: write\n      attestations: write$",
        )
        self.assertEqual(attest.count(
            "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"), 2)
        self.assertIn("subject-path:", attest)
        self.assertIn("sbom-path:", attest)
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 6)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])

    def test_draft_job_has_only_contents_write_and_environment_approval(self):
        publish = self.source.split("  draft-publish:", 1)[1]
        self.assertIn("environment: ${{ inputs.publish_environment }}", publish)
        self.assertRegex(publish, r"(?m)^    permissions:\n      contents: write$")
        self.assertNotIn("id-token: write", publish)
        self.assertNotIn("attestations: write", publish)
        self.assertIn("gh release create", publish)
        self.assertIn("--draft --verify-tag", publish)
        self.assertNotIn("gh release edit", publish)
        self.assertNotIn("gh release upload", publish)




if __name__ == "__main__":
    unittest.main(verbosity=2)
