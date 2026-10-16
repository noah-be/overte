#!/usr/bin/env python3
"""Finite CI37 source admission without executing candidate code.

This deliberately conservative generation binds the complete immutable tree,
including import shadows, discovery membership, subprocess implementations and
native registration inputs. Only a few reviewed data leaves may change bytes.
It does not claim a complete dynamic call graph or supply runtime evidence.
The protected runner must independently capture the actual CI37 environment.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import base64
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import unicodedata

import inputs


ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/ci37-runtime.json"
PINNED_SOURCE = ".github/android-orchestration.json"
DATA_PATH = ".github/branch-cleanup.json"
ENVIRONMENT_SCHEMA = 2
PROFILE = "ubuntu24-ci37-v1"
# Controlled native source capability, never execution evidence. Policy, exact
# future generation and native execution still apply; no CLI override exists.
SOURCE_READY = True
DIAGNOSTIC_KIND = 'ci37-actual-source-diagnostic-v1'
CONTROLLER_KIND = 'ci37-protected-controller-v1'
CONTROLLER_EPOCH = 'ubuntu24-ci37-controller-20261016-v1'
CONTROLLER_MANIFEST = 'ci37-controller-source.json'
SUITES = (
    "producer-proof", "producer-api", "dependency-releases", "project-runner",
    "python-test-runner", "repository-checks", "android-build-inputs",
    "codeql-selection", "ios-build-qualification", "ios-input-selection",
    "repository-policy", "policy-consistency", "documentation-contracts",
    "repository-doctor", "repository-maintenance", "branch-policy",
    "branch-name-guard", "branch-cleanup", "sync-test-reuse",
    "workflow-action-pins", "release-bundle", "workflow-contracts",
    "repository-health", "issue-intake", "project-coverage", "documentation",
    "native-ci-policy", "native-registration", "source-layout", "test-evidence",
    "android-ci", "browser-cpu-selection", "host-producer-preparation",
    "attested-runtime", "android-orchestration", "host-selection",
    "android-owner-transfer",
)
_PRODUCT_QUICK = frozenset({
    "codeql-remediation", "javascript-behavior", "server-console-behavior",
    "device-result-schema", "device-jenkins", "desktop-input-protocol",
    "performance-contracts",
})
_HOST_SUITES = frozenset({
    "device-control-plane-full", "safe-landing-lifecycle", "embedded-web-policy",
    "embedded-web-qml", "web-entity-visibility", "places-native-qml",
    "account-auth-dispatch", "lod-preferences", "goto-dialog-script",
    "recorded-voice-native", "recorded-voice-qml", "snapshot-native", "snapshot-qml",
    "document-tree-native", "obj-material-native", "shared-script-behavior",
})
_REASONS = frozenset({"reviewed-ci-only-inputs", "reviewed-ci-and-package-owners"})
_PACKAGE_LOCKS = frozenset({
    "browser-client/package-lock.json", "script-archive/marketplace/S3Server/package-lock.json",
})
# Keep membership and ordinary mode/type for these exact documentation leaves.
# The fixed documentation validator reads Markdown links/headings as data; the
# policy display check compares a generated text block in PROJECT_TESTING.md.
# Neither executes documentation snippets. All workflow bytes remain bound:
# reviewed suite implementations do execute some YAML run snippets.
# Additions and every neighboring path remain bound.
_VARIABLE_DATA = frozenset({
    "README.md", "tests/PROJECT_TESTING.md", "docs/BRANCH_WORKFLOW.md",
})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema", "enabled", "profile", "epoch", "suites", "definition_digest", "generation_digest",
    "not_before", "max_age_seconds",
})
_PERMANENT = (
    "main", "android-main", "android-phone", "android-vr", "android-vr-pico", "apple-main", "apple-ios",
)
_CLEANUP_FIELDS = frozenset({
    "schema", "repository", "repository_id", "permanent_branches", "holds", "keep_label", "artifact_retention_days",
})


class CIProfileError(ValueError):
    """The finite CI37 source/profile contract is unavailable; use the full owner."""


def _require(condition, message):
    if not condition:
        raise CIProfileError(message)


def _digest(value):
    return "sha256:" + hashlib.sha256(inputs._canonical(value)).hexdigest()


def _validate_policy(value):
    _require(isinstance(value, dict) and set(value) in (_FIELDS, (_FIELDS-{'generation_digest'})|{'generation_kind'}),
             "unsupported CI37 policy fields")
    controller = 'generation_kind' in value
    if controller:
        _require(value['generation_kind']==CONTROLLER_KIND and value.get('epoch')==CONTROLLER_EPOCH,
                 'unsupported protected-controller generation namespace or epoch')
    _require(type(value["schema"]) is int and value["schema"] == 1
             and type(value["enabled"]) is bool and value["profile"] == PROFILE,
             "unsupported CI37 policy profile")
    _require(isinstance(value["epoch"], str)
             and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", value["epoch"]),
             "unsupported CI37 policy epoch")
    _require(isinstance(value["not_before"], str)
             and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value["not_before"]),
             "CI37 policy requires a fixed UTC admission boundary")
    try:
        datetime.fromisoformat(value["not_before"][:-1] + "+00:00")
    except ValueError:
        raise CIProfileError("CI37 policy admission boundary is invalid") from None
    _require(type(value["max_age_seconds"]) is int and 0 < value["max_age_seconds"] <= 259200,
             "unsupported CI37 validity policy")
    _require(value["suites"] == list(SUITES), "CI37 policy must retain the exact ordered inventory")
    for name in ('definition_digest',) if controller else ("definition_digest", "generation_digest"):
        _require(isinstance(value[name], str) and _DIGEST.fullmatch(value[name]),
                 "missing reviewed CI37 generation identity")
    return value


def controller_paths():
    """Fixed protected loader closure; never paths supplied by a candidate."""
    import source_admission
    return sorted(set(source_admission.CONTROLLERS)|set(source_admission.IMPORT_MEMBERS))


def _controller_tree_identity(entries):
    """Reconstruct a complete ordinary Git tree without invoking candidate Git."""
    inputs._validate_tree(entries)
    root={}
    for name,entry in entries.items():
        _require(entry['type']=='blob' and entry['mode'] in {'100644','100755'},
                 'controller manifest contains a nonordinary object')
        node=root;parts=name.split('/')
        for part in parts[:-1]:
            node=node.setdefault(part,{})
            _require(type(node) is dict, 'controller tree has a file/directory collision')
        _require(parts[-1] not in node, 'controller tree has a duplicate/collision')
        node[parts[-1]]=(entry['mode'],entry['sha'])
    def tree(node):
        raw=b''
        for name,value in sorted(node.items(),key=lambda item:(item[0]+('/' if type(item[1]) is dict else '')).encode('utf-8')):
            mode,oid=('40000',tree(value)) if type(value) is dict else value
            raw+=mode.encode()+b' '+name.encode('utf-8')+b'\0'+bytes.fromhex(oid)
        return hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    _require(bool(entries), 'controller manifest has no complete source')
    return tree(root)


def capture_controller_manifest(root, trusted_source):
    """Called only after native B/D admission, on the actual protected checkout."""
    tree,entries=_diagnostic_source(root,trusted_source)
    _require(_controller_tree_identity(entries)==tree, 'actual controller tree does not match immutable Git')
    size=_controller_git(root,'cat-file','-s',trusted_source)
    _require(re.fullmatch(rb'[0-9]{1,7}\n',size) and 0<int(size)<=1_000_000,
             'controller commit object exceeds its bound')
    commit=_controller_git(root,'cat-file','commit',trusted_source)
    _require(len(commit)==int(size),'controller commit object size changed')
    actual_commit=hashlib.sha1(b'commit '+str(len(commit)).encode()+b'\0'+commit).hexdigest()
    _require(actual_commit==trusted_source,'actual controller commit differs from admitted native source')
    value={'schema':1,'kind':CONTROLLER_KIND,'source_commit':actual_commit,'source_tree':tree,
           'commit_object':base64.b64encode(commit).decode('ascii'),'entries':entries}
    _validate_controller_manifest(value,root)
    return value


def _validate_controller_manifest(value, root):
    """Authenticate the fixed projected files and complete import lookup.

    Manifest ownership/native D provenance is supplied by the root supervisor;
    this pure parser never turns a candidate map into source authority.
    """
    import source_admission
    _require(type(value) is dict and set(value)=={'schema','kind','source_commit','source_tree','commit_object','entries'}
        and type(value['schema']) is int and value['schema']==1 and value['kind']==CONTROLLER_KIND
        and type(value['source_commit']) is str and re.fullmatch('[0-9a-f]{40}',value['source_commit'])
        and value['source_commit']!='0'*40 and type(value['source_tree']) is str
        and re.fullmatch('[0-9a-f]{40}',value['source_tree']), 'controller source manifest is malformed')
    encoded=value['commit_object']
    _require(type(encoded) is str and 0<len(encoded)<=1_333_336, 'controller commit encoding exceeds its bound')
    try:commit=base64.b64decode(encoded,validate=True)
    except (ValueError,UnicodeError):raise CIProfileError('controller commit encoding is invalid') from None
    _require(0<len(commit)<=1_000_000 and base64.b64encode(commit).decode('ascii')==encoded
        and hashlib.sha1(b'commit '+str(len(commit)).encode()+b'\0'+commit).hexdigest()==value['source_commit']
        and commit.split(b'\n',1)[0]==b'tree '+value['source_tree'].encode('ascii'),
        'controller immutable commit/tree identity differs')
    entries=value['entries']
    _require(type(entries) is dict and 0<len(entries)<=200_000
        and len(inputs._canonical(value))<=32_000_000, 'controller source manifest exceeds its bound')
    _require(_controller_tree_identity(entries)==value['source_tree'], 'controller manifest tree identity differs')
    files={}
    for name in controller_paths():
        expected=entries.get(name)
        mode='100755' if name=='tests/run-project-tests.py' else '100644'
        _require(type(expected) is dict and expected.get('type')=='blob' and expected.get('mode')==mode,
                 'controller source closure is missing or nonordinary')
        raw,actual=source_admission.actual_bytes(root,name)
        _require(actual==expected, 'actual projected controller source differs from immutable D')
        files[name]=actual
    imports={path:entry for path,entry in entries.items()
        if any(path==prefix or path.startswith(prefix+'/') for prefix in source_admission.IMPORT_ROOTS)}
    _require(set(imports)==set(source_admission.IMPORT_MEMBERS), 'controller import membership is not reviewed')
    directories={str(parent) for path in imports for parent in Path(path).parents
        if any(str(parent)==prefix or str(parent).startswith(prefix+'/') for prefix in source_admission.IMPORT_ROOTS)}
    _require(source_admission.actual_import_inventory(root)=={'files':imports,'directories':sorted(directories)},
             'actual projected import lookup differs from immutable D')
    return entries


def controller_generation(entries, registry):
    """Dynamic actual protected D identity in a distinct runtime namespace."""
    import source_admission
    inputs._validate_tree(entries)
    imports={path for path in entries if any(path==prefix or path.startswith(prefix+'/')
        for prefix in source_admission.IMPORT_ROOTS)}
    _require(imports==set(source_admission.IMPORT_MEMBERS), 'controller generation lookup membership is unknown')
    rows=[]
    for name in controller_paths():
        entry=entries.get(name);mode='100755' if name=='tests/run-project-tests.py' else '100644'
        _require(type(entry) is dict and entry.get('mode')==mode and entry.get('type')=='blob',
                 'controller generation is incomplete or nonordinary')
        item={'path':name,**entry}
        # These exact existing cycles retain independent raw policy/Android
        # pin checks. No candidate execution-source fingerprint is projected.
        if name in {POLICY,PINNED_SOURCE}:item.pop('sha')
        rows.append(item)
    return _digest({'kind':CONTROLLER_KIND,'entries':rows,'definition_digest':definition_digest(registry)})


def _controller_git(root,*arguments):
    environment={name:value for name,value in os.environ.items() if not name.startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1')
    raw=subprocess.check_output(['/usr/bin/git','--no-replace-objects','-c','core.hooksPath=/dev/null',
        '-c','core.fsmonitor=false','-c','maintenance.auto=false','-c','gc.auto=0',
        '-c','safe.directory='+str(root),*arguments],cwd=root,env=environment,
        stderr=subprocess.PIPE,timeout=30)
    _require(len(raw)<=1_000_000,'controller Git object exceeds its byte bound')
    return raw


def _actual_controller_manifest(root):
    source=_controller_git(root,'rev-parse','--verify','HEAD^{commit}').decode('ascii').strip()
    return capture_controller_manifest(root,source)


def load_controller_projection(root):
    """Internal probe input from the supervisor's sealed root-owned projection."""
    root=Path(root);path=root/CONTROLLER_MANIFEST
    _require(root.is_absolute() and '..' not in root.parts, 'controller projection root is invalid')
    current=Path(root.anchor)
    for part in path.parts[1:]:
        current/=part
        _require(not current.is_symlink(), 'controller projection contains an alias')
    info=path.stat()
    _require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1
        and stat.S_IMODE(info.st_mode)==0o444 and 0<info.st_size<=32_000_000,
        'controller manifest is not sealed root-owned ordinary input')
    raw=path.read_bytes();_require(len(raw)<=32_000_000,'controller manifest exceeds its byte bound')
    value=json.loads(raw,object_pairs_hook=inputs._unique_object)
    _validate_controller_manifest(value,root)
    return value


def load_policy(root=ROOT):
    """Read the fixed trusted policy, including its disabled preparation state."""
    path = Path(root)
    try:
        for component in Path(POLICY).parts:
            path /= component
            _require(not path.is_symlink(), "CI37 trusted policy must not contain aliases")
        _require(path.is_file() and path.stat().st_size <= 32_000, "CI37 trusted policy is unavailable")
        raw = path.read_bytes()
        _require(len(raw) <= 32_000, "CI37 trusted policy is oversized")
        value = json.loads(raw, object_pairs_hook=inputs._unique_object)
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, CIProfileError):
            raise
        raise CIProfileError("CI37 trusted policy is invalid") from None
    return _validate_policy(value)


def policy_identity(policy):
    """Identify the strict policy; protected controller identity also binds bytes."""
    return _digest(_validate_policy(policy))


def _pinned_source_entry(root):
    """Read the one fixed protected leaf that participates in another digest.

    Its complete raw bytes, ordinary mode and every path component are checked.
    It is never candidate data, a supplied exclusion map or an environment proof.
    The repository uses SHA1 Git object identities; other object formats fail.
    """
    path = Path(root)
    _require(path.is_absolute() and ".." not in path.parts, "CI37 pinned source requires a fixed protected root")
    try:
        current = Path(path.anchor)
        for component in (*path.parts[1:], *Path(PINNED_SOURCE).parts):
            current /= component
            _require(not current.is_symlink(), "CI37 pinned source must not contain aliases")
        info = current.stat()
        _require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o111 and info.st_size <= 1_000_000,
                 "CI37 pinned source must be a bounded ordinary nonexecutable file")
        raw = current.read_bytes()
        _require(len(raw) <= 1_000_000, "CI37 pinned source exceeds its byte bound")
    except OSError:
        raise CIProfileError("CI37 pinned source is unavailable") from None
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return {"mode": "100644", "type": "blob", "sha": hashlib.sha1(header + raw).hexdigest()}


def _hold_branch(value):
    """Conservative pure Git branch syntax; never invoke Git for candidate data."""
    if not isinstance(value,str) or not value or value in {"@","HEAD"} or value.startswith("-"):
        return False
    if any(unicodedata.category(character) in {"Cc","Cf","Cs"} or character.isspace()
           or character in "~^:?*[\\" for character in value):
        return False
    try:
        if len(value.encode("utf-8")) > 240:
            return False
    except UnicodeError:
        return False
    return not (".." in value or "@{" in value or value.endswith(".") or any(
        not part or part.startswith(".") or part.endswith(".lock") for part in value.split("/")))


def _cleanup_data(entry, read_blob):
    """Authenticate and validate the one admitted immutable cleanup data blob."""
    _require(isinstance(entry,dict) and entry.get("mode") == "100644" and entry.get("type") == "blob"
             and isinstance(entry.get("sha"),str) and re.fullmatch(r"[0-9a-f]{40}",entry["sha"]),
             "CI37 cleanup data requires an ordinary immutable SHA1 blob")
    try:
        raw = read_blob(entry["sha"])
    except Exception:
        raise CIProfileError("CI37 immutable cleanup data is unavailable") from None
    _require(type(raw) is bytes and len(raw) <= 64_000, "CI37 cleanup data exceeds its immutable byte bound")
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    _require(hashlib.sha1(header+raw).hexdigest() == entry["sha"], "CI37 cleanup bytes differ from authenticated source")
    try:
        value = json.loads(raw.decode("utf-8"),object_pairs_hook=inputs._unique_object,
            parse_constant=lambda _value: _require(False,"CI37 cleanup data contains a nonfinite number"))
    except (ValueError,UnicodeError,RecursionError):
        raise CIProfileError("CI37 cleanup data is not strict JSON") from None
    _require(isinstance(value,dict) and set(value) == _CLEANUP_FIELDS, "unsupported CI37 cleanup data fields")
    _require(type(value["schema"]) is int and value["schema"] == 1
             and value["repository"] == "noah-l-frank/overte"
             and type(value["repository_id"]) is int and value["repository_id"] == 1319052603
             and value["permanent_branches"] == list(_PERMANENT)
             and value["keep_label"] == "keep-branch"
             and type(value["artifact_retention_days"]) is int and value["artifact_retention_days"] == 30,
             "CI37 cleanup data changes a fixed policy contract")
    holds = value["holds"]
    _require(isinstance(holds,dict) and len(holds) <= 128, "CI37 cleanup holds exceed their reviewed bound")
    _require(all(_hold_branch(branch) and isinstance(reason,str) and 0 < len(reason) <= 512 and reason.strip()
        and not any(unicodedata.category(character) in {"Cc","Cf","Cs"} for character in reason)
        for branch,reason in holds.items()), "CI37 cleanup holds contain unsupported branch names or reasons")


def definition_digest(registry):
    """Bind commands, contexts, closures, reviewed imports and control inputs."""
    try:
        inputs._validate_registry(registry)
    except (TypeError, ValueError):
        raise CIProfileError("CI37 requires the complete trusted registry") from None
    suites = registry["suites"]
    expected = tuple(name for name, suite in suites.items()
                     if suite["layer"] == "quick" and name not in _PRODUCT_QUICK)
    _require(expected == SUITES, "trusted quick inventory is not the reviewed CI37 generation")
    _require(suites.keys() == set(SUITES) | _PRODUCT_QUICK | _HOST_SUITES
             and all(suites[name]["layer"] == "quick" for name in _PRODUCT_QUICK)
             and all(suites[name]["layer"] == "host" for name in _HOST_SUITES),
             "CI37 requires a complete registry with its separate product owners")
    return _digest({"suites": [{"name": name, "definition": suites[name]} for name in SUITES],
                    "registry_inventory": list(suites),
                    "control_inputs": registry["control_inputs"]})


def generation(tree, registry):
    """Bind an immutable broad source superset and all lookup membership.

    The CI37 policy is omitted to avoid a self-cycle. The fixed Android leaf
    omits its SHA to break another anchor cycle; admission pins its complete
    bytes against the protected root and both immutable trees. The one cleanup
    data leaf omits its SHA only with separate immutable-blob authentication and
    closed-schema admission. Both retain path/mode/type. These exceptions never
    narrow ordinary suite fingerprints or protected controller identity.
    """
    try:
        inputs._validate_tree(tree)
    except (TypeError, ValueError):
        raise CIProfileError("CI37 requires a complete immutable source inventory") from None
    _require(bool(tree), "CI37 source inventory is empty")
    entries = []
    for path, entry in sorted(tree.items()):
        _require(entry["mode"] in {"100644", "100755"} and entry["type"] == "blob",
                 "CI37 source inventory contains an alias or nonregular entry")
        if path == POLICY:
            _require(entry["mode"] == "100644", "CI37 policy must be an ordinary nonexecutable blob")
            continue
        item = {"path": path, **entry}
        if path in _VARIABLE_DATA or path in {PINNED_SOURCE,DATA_PATH}:
            _require(entry["mode"] == "100644", "CI37 reviewed data must remain nonexecutable")
            del item["sha"]
        entries.append(item)
    return _digest({"kind": "ci37-conservative-source-v1", "entries": entries,
                    "definition_digest": definition_digest(registry)})


def validate_selection(selection, candidate_tree, trusted_tree, registry, *, target="main",
                       regular=True, unknown=False, policy=None, require_enabled=True, root=ROOT, read_blob=None,
                       controller_manifest=None):
    """Admit only the independently recomputed main CI37 selection and generation.

    Production callers leave require_enabled at its default. False is for pure
    source preparation/tests and yields no runtime or execution qualification.
    The independent router still owns changed-path and workflow authorization.
    read_blob is a trusted bounded reader from one immutable object SHA to raw
    bytes; this guard independently verifies both cleanup objects and schemas.
    """
    value = load_policy(root) if policy is None else _validate_policy(policy)
    _require(type(require_enabled) is bool, "invalid CI37 source preparation mode")
    if require_enabled:
        _require(SOURCE_READY and value["enabled"] is True, "CI37 runtime profile is not activated")
    _require(target == "main" and regular is True and unknown is False,
             "CI37 requires a known regular main plan")
    required = {"suites", "reason", "full_host", "include_platform"}
    _require(isinstance(selection, dict) and required <= selection.keys()
             and selection.keys() <= required | {"package_owned_paths"},
             "unsupported CI37 selection fields")
    _require(selection["suites"] == list(SUITES) and selection["full_host"] is False
             and selection["include_platform"] is False and isinstance(selection["reason"], str)
             and selection["reason"] in _REASONS,
             "CI37 requires the exact independently selected 37 owners")
    packages = selection.get("package_owned_paths", [])
    _require(isinstance(packages, list)
             and all(isinstance(path, str) and path in _PACKAGE_LOCKS for path in packages)
             and packages == sorted(set(packages))
             and bool(packages) == (selection["reason"] == "reviewed-ci-and-package-owners"),
             "CI37 package work requires its finite independent owner")
    definitions = definition_digest(registry)
    _require(definitions == value["definition_digest"], "CI37 command definitions changed")
    controller=value.get('generation_kind')==CONTROLLER_KIND
    if controller:
        for tree in (candidate_tree,trusted_tree):
            inputs._validate_tree(tree)
            _require(bool(tree) and all(entry['mode'] in {'100644','100755'} and entry['type']=='blob'
                for entry in tree.values()), 'controller CI37 requires complete ordinary candidate inventories')
            _require(all(tree.get(path,{}).get('mode') in {'100644','100755'}
                and tree[path]['type']=='blob' for name in SUITES for path in registry['suites'][name]['closure']['required']),
                'controller CI37 selected owner implementation is missing')
        manifest=_actual_controller_manifest(root) if controller_manifest is None else controller_manifest
        actual=_validate_controller_manifest(manifest,root)
        raw,actual_policy=_diagnostic_file(root,POLICY)
        _require(_validate_policy(json.loads(raw,object_pairs_hook=inputs._unique_object))==value,
                 'controller policy differs from actual protected bytes')
        registry_raw,registry_entry=_diagnostic_file(root,'.github/test-suites.json')
        _require(inputs._validate_registry(json.loads(registry_raw,object_pairs_hook=inputs._unique_object))==registry
            and all(tree.get('.github/test-suites.json')==registry_entry for tree in (candidate_tree,trusted_tree,actual))
            and actual.get(POLICY)==actual_policy==trusted_tree.get(POLICY)==candidate_tree.get(POLICY)
            and all(tree.get('tests/platform-profile.json')==actual.get('tests/platform-profile.json')
                for tree in (candidate_tree,trusted_tree)), 'controller candidate declarations differ from actual D')
        _require(actual.get('tests/platform-profile.json',{}).get('sha')=='d63537504c20204de9d35d9be61da72a56df59c3',
                 'controller CI37 requires the exact empty shared platform')
        candidate_generation=controller_generation(actual,registry)
        _require(controller_generation(trusted_tree,registry)==candidate_generation,
                 'supplied trusted context differs from actual D controllers')
    else:
        _require(controller_manifest is None, 'legacy whole-tree profile does not accept controller manifests')
        candidate_generation = generation(candidate_tree, registry)
        trusted_generation = generation(trusted_tree, registry)
        _require(candidate_generation == trusted_generation == value["generation_digest"],
                 "CI37 executable, discovery or lookup generation changed")
    old_policy, new_policy = trusted_tree.get(POLICY), candidate_tree.get(POLICY)
    _require(isinstance(old_policy, dict) and old_policy == new_policy
             and old_policy["mode"] == "100644" and old_policy["type"] == "blob",
             "CI37 policy requires identical ordinary trusted and candidate entries")
    pinned = _pinned_source_entry(root)
    _require(candidate_tree.get(PINNED_SOURCE) == trusted_tree.get(PINNED_SOURCE) == pinned,
             "CI37 fixed pinned source differs from the protected root or immutable trees")
    _require(callable(read_blob), "CI37 cleanup admission requires a trusted immutable blob reader")
    # Read both complete authenticated objects on every route, even when their
    # OIDs match. No checked-out candidate file or claimed data class is proof.
    for tree in (trusted_tree,candidate_tree):
        _cleanup_data(tree.get(DATA_PATH),read_blob)
    # Data contents belong to suite fingerprints and native source binding,
    # not runtime E: original and current admitted holds may legitimately differ.
    binding={"schema": ENVIRONMENT_SCHEMA, "profile": PROFILE, "epoch": value["epoch"],
            "suites": list(SUITES), "definition_digest": definitions,
            "generation_digest": candidate_generation, "policy_digest": policy_identity(value),
            "pinned_source": {"path": PINNED_SOURCE, **pinned}}
    if controller:binding['generation_kind']=CONTROLLER_KIND
    return binding


def _diagnostic_source(source_root, source):
    """Read an actual immutable diagnostic checkout, never a supplied tree hint."""
    _require(type(source) is str and re.fullmatch(r'[0-9a-f]{40}', source)
             and source != '0'*40, 'diagnostic source commit is unavailable')
    _require(isinstance(source_root,(str,Path)), 'diagnostic source root is unavailable')
    source_root = Path(source_root)
    _require(source_root.is_absolute() and '..' not in source_root.parts, 'diagnostic source root is invalid')
    current = Path(source_root.anchor)
    for part in source_root.parts[1:]:
        current /= part
        _require(not current.is_symlink(), 'diagnostic source root contains an alias')
    environment = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                       GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1')
    def read(*arguments):
        value = subprocess.run(['git','--no-replace-objects','-c','core.hooksPath=/dev/null',
            '-c','core.fsmonitor=false','-c','maintenance.auto=false','-c','gc.auto=0',
            '-c','safe.directory='+str(Path(source_root)),*arguments],cwd=source_root,env=environment,
            check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30).stdout
        _require(len(value) <= 32_000_000, 'diagnostic source exceeds its immutable bound')
        return value
    try:
        _require(read('rev-parse','--verify','HEAD^{commit}').decode().strip() == source,
                 'diagnostic actual HEAD differs from its protected source')
        tree_oid = read('rev-parse','--verify',source+'^{tree}').decode().strip()
        _require(re.fullmatch(r'[0-9a-f]{40}',tree_oid), 'diagnostic tree identity is unavailable')
        tree = {}
        for record in read('ls-tree','-rz','--full-tree',source).split(b'\0'):
            if not record: continue
            fields,path = record.split(b'\t',1)
            mode,kind,oid = fields.decode().split()
            path = path.decode('utf-8')
            _require(path not in tree and len(tree) < 200_000, 'diagnostic inventory is ambiguous')
            tree[path] = {'mode':mode,'type':kind,'sha':oid}
        inputs._validate_tree(tree)
        _require(tree and all(e['mode'] in {'100644','100755'} and e['type']=='blob'
                             for e in tree.values()), 'diagnostic inventory is not complete ordinary source')
        return tree_oid,tree
    except (OSError,subprocess.SubprocessError,UnicodeError,ValueError) as error:
        if isinstance(error,CIProfileError): raise
        raise CIProfileError('diagnostic immutable source is unavailable') from error


def _diagnostic_file(root, relative):
    path = Path(root)
    _require(path.is_absolute() and '..' not in path.parts, 'diagnostic protected root is invalid')
    current = Path(path.anchor)
    for part in (*path.parts[1:],*Path(relative).parts):
        current /= part
        _require(not current.is_symlink(), 'diagnostic protected input contains an alias')
    info = current.stat()
    _require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o111 and info.st_size <= 1_000_000,
             'diagnostic protected input is not bounded ordinary data')
    raw = current.read_bytes()
    _require(len(raw) <= 1_000_000, 'diagnostic protected input exceeds its bound')
    return raw,{'mode':'100644','type':'blob','sha':hashlib.sha1(
        b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}


def _diagnostic_selection(selection, candidate_tree, trusted_tree, registry, *, source, source_root, root=ROOT,
                         target='main', read_blob=None, controller_manifest=None):
    """Measure exact actual source with a distinct, production-inadmissible binding.

    Shipping future-generation policy remains untouched. Only this manual API
    derives a local generation expectation from the independently read checkout.
    Both the parent and protected probe call it; no producer accepts its result.
    """
    tree_oid,actual = _diagnostic_source(source_root,source)
    _require(actual == candidate_tree == trusted_tree, 'diagnostic supplied inventory differs from actual source')
    raw,entry = _diagnostic_file(root,POLICY)
    _require(actual.get(POLICY)==entry, 'diagnostic policy differs from actual immutable source')
    policy = _validate_policy(json.loads(raw,object_pairs_hook=inputs._unique_object))
    registry_raw,registry_entry = _diagnostic_file(root,'.github/test-suites.json')
    _require(actual.get('.github/test-suites.json') == registry_entry
             and inputs._validate_registry(json.loads(registry_raw,object_pairs_hook=inputs._unique_object)) == registry,
             'diagnostic registry differs from actual protected source')
    _require(all(actual.get(path,{}).get('mode') in {'100644','100755'}
        and actual[path]['type']=='blob' for name in SUITES for path in registry['suites'][name]['closure']['required']),
        'diagnostic fixed owner implementation is missing')
    derived = policy if policy.get('generation_kind')==CONTROLLER_KIND else {**policy,'generation_digest':generation(actual,registry)}
    admitted = validate_selection(selection,actual,actual,registry,target=target,policy=derived,
        require_enabled=False,root=root,read_blob=read_blob,controller_manifest=controller_manifest)
    return {'kind':DIAGNOSTIC_KIND,'source_commit':source,'source_tree':tree_oid,
            'production_policy_digest':policy_identity(policy),'actual_selection':admitted}


def diagnostic_selection(*args, **kwargs):
    """Fixed diagnostic entrypoint; malformed source never becomes a measurement."""
    try:
        return _diagnostic_selection(*args,**kwargs)
    except CIProfileError:
        raise
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,subprocess.SubprocessError) as error:
        raise CIProfileError('diagnostic actual source binding is unavailable') from error
