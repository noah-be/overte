# Fixed owned-staging operation diagnostics

The observed fork atomic-settings workflow stops before its signed-dependency/native contract steps with only `owned-atomic-dependency-staging-refused`. Its cause remains unknown. This isolated proposal adds one fixed JSON record to normal stage stdout on failure or success. It creates no new artifact or debug endpoint and does not install dependencies, change a workflow, import archive keys or run services.

All existing commit/fork admission, fixed HTTPS paths, redirect refusal, byte limits, SHA256/size checks, host keyring ownership/mode/regular-file bounds, trusted signature fingerprint, signed index/package stanza, archive layout/member and exact executable gates remain unchanged. The existing three positional `signed_dependency` arguments and its success/exception contracts remain supported. Only an optional internal keyword phase callback is added. The metadata, source pin sets and existing signed-dependency tests are byte-identical.

Phases cover reviewed source, authorized fork, private temporary root/directories, fixed helper copying, each of the three downloads, downloaded digests/size, private writes, existing keyring admission, signature execution/output/validation, signed index/package validation, archive listing/layout/held output creation/member extraction/decode, executable validation/write, proof and workflow environment operations. Labels are internal fixed enums. A missing archive output directory is distinguished from a missing extraction tool rather than incorrectly declaring that every FileNotFoundError names a tool.

Failure categories come only from fixed exception classes plus the phase. An HTTP status is included only if its actual code is an integer from 100 through 599; booleans, floats, strings and out-of-range values are not reflected. No exception text, filenames, URLs, profile names, argv, key fingerprints, source values, credentials, environment values or subprocess streams are included. Unknown exceptions remain `unexpected-error`. Unknown progress values are rejected. The CLI retains nonzero exit and the original fixed stderr refusal. Successful staging emits a distinct fixed `completed:true` record only after the original main operation returns; this is not completion of the native workflow or product.

Git/archive/decompression subprocess stderr is captured privately instead of being inherited into the public console. On the failure boundary an owned HTTPError response is explicitly closed before exception finalization: a real Python3.14 unclosed HTTPError can otherwise emit a ResourceWarning containing its private reason even when the JSON projection is safe. The pure projection and signed-dependency API do not acquire ownership of their caller's exception; external callers remain responsible for their HTTP response cleanup.

## Verification

Nineteen new contracts and the seven unchanged stage/curation contracts pass, including the actual cached gpgv -> signed index -> package -> extracted executable chain, exact source/fork refusal before private allocation, each download's failure phase, missing keyring versus missing tool, signature/extraction refusal, real private environment writing, actual CLI nonzero output, invalid HTTP values, unknown exceptions that cannot be stringified, and the unclosed-resource privacy regression. Test logs and real UTC intervals are in `CPU_EVIDENCE.json`. All requests are satisfied from previously reviewed cached bodies; no new network, native, browser or service workload was launched. Signature success uses the parent's existing reviewed test keyring because the Fedora host lacks the normal Ubuntu system keyring. The unchanged production keyring path still must succeed in hosted Ubuntu.

Parent integration copies `stage.py` plus `test_stage_failure.py` and applies the exact reviewed `stage.patch`; optionally place this guide in the lab directory. Existing `test_*.py` workflow discovery automatically includes the new file after staging. Commands use the same existing `ATOMIC_DIAGNOSTIC_CACHE` and `ATOMIC_DIAGNOSTIC_TEST_KEYRING` review inputs as the original tests:

```sh
python3 -B -W error::ResourceWarning -m unittest discover -s browser-client/lab/atomic-provisioning -p 'test_stage_failure.py'
python3 -B -m unittest discover -s browser-client/lab/atomic-provisioning -p 'test_stage_curate.py'
```

A parent-owned new exact-source hosted execution is needed to establish the actual failed operation/category. Local signed download success and absence of a local Ubuntu system keyring do not identify the earlier hosted cause. This proposal was substantially authored with AI assistance and awaits independent parent review.
