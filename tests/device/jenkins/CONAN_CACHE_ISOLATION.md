# Isolated Android build workspaces and Conan caches

Phone and Pico builds must not write to the same Conan 2 home concurrently.
Conan's cache contains mutable recipe revisions, package metadata, temporary
build state, generated profiles, and per-package locks. In addition, some
Android dependency jobs temporarily patch cached Qt sources and recipes. A
package-level lock does not turn that whole tree into a transaction, so two
different build graphs can observe or replace partially updated state.

Conan isolation is necessary but not sufficient. Phone and Pico also write to
overlapping paths in one checkout: Gradle project output, `android/common/conan`
generator directories, shared runtime overrides, and Pico host/compatibility
staging. Therefore a real parallel build must use
`android_build_workspace.py`, which gives the complete child process its own
commit-exact checkout, Gradle home, temporary directories, and role Conan home.
Running only `conan_cache_manager.py run` around a build in a shared checkout is
not a supported parallel-build configuration.

The existing entry points already honor `CONAN_HOME`:

- `android/vr/pico/build.sh` resolves its cache from `CONAN_HOME` and all Conan
  child processes inherit that environment;
- `android/phone/build-phone-qt-16k.sh` and
  `android/phone/prepare-phone-16k-conan-deps.sh` do the same;
- the Phone build also has `PHONE_SHARED_CONAN_HOME` compatibility paths. For
  the Phone role, the manager pins that variable to the same Phone-only home
  so it cannot fall back to `~/.conan2` or Pico's writable home.

No entry point has to be edited. The workspace wrapper exports all private
paths only to its child and retains the role lock until that child exits.

## Required layout and permissions

Choose one absolute, account-private root that is not the checkout, a device
workspace, or `~/.conan2`. Do not include an ADB serial, Pico identifier,
Jenkins target credential, or other physical-device identifier in the root.
For example:

```text
/srv/jenkins-private/overte-android-builds/
  .overte-android-build-root-v1
  workspaces/
    android-phone-*/      # one private, commit-exact checkout per child
    android-pico-*/

/srv/jenkins-private/overte-conan/
  .overte-conan-cache-root-v1
  homes/
    android-phone/       # writable only by Phone jobs
    android-pico/        # writable only by Pico jobs
  locks/
    android-phone.lock
    android-pico.lock
  tmp/
```

The managers create roots and homes with mode `0700`, files with `0600`, and a
process umask of `077`. They reject a symlink in any existing path component,
foreign-owned managed paths, an
unmarked non-empty root, an unsupported role, a busy same-role cache, a root
inside the default Conan cache, and paths containing a selector found in the
known private target environment variables. Error messages never echo such a
selector or a cache path.

It never deletes, renames, imports, or changes anything in `~/.conan2`. There
is intentionally no reset or prune operation.

## Build invocation

Use the workspace wrapper for builds. The source must have no tracked changes;
the wrapper clones its exact `HEAD` without hardlinks and never deletes or
modifies the source checkout. The first command may run while the second is
running because both their checkout state and Conan homes differ:

```bash
python3 tests/device/jenkins/android_build_workspace.py \
  --source "$PWD" \
  --build-root /srv/jenkins-private/overte-android-builds \
  --conan-root /srv/jenkins-private/overte-conan \
  --role android-phone \
  --artifact-dir /srv/jenkins-private/artifacts/phone-42

python3 tests/device/jenkins/android_build_workspace.py \
  --source "$PWD" \
  --build-root /srv/jenkins-private/overte-android-builds \
  --conan-root /srv/jenkins-private/overte-conan \
  --role android-pico \
  --artifact-dir /srv/jenkins-private/artifacts/pico-42
```

A second process for the same role fails immediately instead of sharing its
writable home. Different roles can run together. By default the private
checkout is removed only after the child and optional fixed-path APK export
finish; `--keep-workspace` is reserved for trusted diagnostics. The wrapper
does not print the command or private state paths. Build jobs must likewise
avoid printing the complete environment.

For a later Jenkins build Pipeline, keep the root in trusted node
configuration and pass the role as a constant selected by the job definition:

```groovy
sh '''#!/bin/sh
set -eu
set +x
exec python3 tests/device/jenkins/android_build_workspace.py \
  --source "$WORKSPACE" \
  --build-root "$OVERTE_ANDROID_BUILD_ROOT" \
  --conan-root "$OVERTE_CONAN_CACHE_ROOT" \
  --role android-phone \
  --artifact-dir "$WORKSPACE_TMP/android-phone-apk"
'''
```

Do not derive the role or either managed root from `DEVICE_RESOURCE`, an ADB
serial, or the target-selector credential. `android-phone` and `android-pico`
are the only accepted role names. Use one invocation of the default `all`
command, rather than separate Jenkins steps whose generated checkout state
would need to be shared.

## Safe environment-file output

`prepare` is available when a Jenkins step needs `KEY=value` entries before
starting a separately locked build step:

```bash
set +x
python3 tests/device/jenkins/conan_cache_manager.py prepare \
  --root "$OVERTE_CONAN_CACHE_ROOT" \
  --role android-phone \
  --env-file "$WORKSPACE_TMP/conan-phone.env"
```

The file is `0600`, contains only a format marker, the fixed role,
`CONAN_HOME`, and the Phone-only `PHONE_SHARED_CONAN_HOME` where applicable.
It may be passed to Jenkins `withEnv(readFile(...).readLines())`.
Write it below Jenkins' private temporary workspace and do not archive it.
`prepare` releases its local role lock after writing. It is suitable only for
non-build cache inspection or integration glue. An actual Android build must
still use `android_build_workspace.py`; a Jenkins lock around one shared
checkout does not permit Phone and Pico to run in parallel.

## Optional immutable seed

A seed saves downloads without reintroducing a shared writable cache. It must
be a versioned, owner-private and recursively read-only directory (directories
`0500`, regular files `0400`) with no symlinks or special files. It must not be
`~/.conan2`. Every seed consumer must name the same absolute lock file outside
the seed:

```bash
python3 tests/device/jenkins/android_build_workspace.py \
  --source "$PWD" \
  --build-root /srv/jenkins-private/overte-android-builds \
  --conan-root /srv/jenkins-private/overte-conan \
  --role android-phone \
  --seed /srv/jenkins-private/conan-seeds/2026-08-25 \
  --seed-lock /srv/jenkins-private/conan-seeds/seed.lock
```

On first use of a role, the manager takes a non-blocking shared seed lock,
verifies the complete seed is physically read-only, copies it with GNU
`cp --archive --reflink=auto`, verifies the seed metadata did not change, and
makes only the role copy private and writable. Reflinks give copy-on-write
isolation where the filesystem supports them; GNU `cp` safely falls back to a
normal copy otherwise. Existing role homes are never refreshed implicitly.

Seed publication is deliberately outside build jobs. A publisher must take an
exclusive lock on the exact same seed lock, populate a new versioned staging
directory from a quiescent producer cache, make directories `0500` and regular
files `0400`, and only then publish the new version. Never mutate or replace a
published seed in place. Because readers take a shared lock and fail rather
than wait when the exclusive lock is held, seed publication and seed copying
cannot overlap when all producers use this contract.

## Device-free verification

These tests use only temporary directories and small real Git/build-script
fixtures; they do not invoke Conan, Gradle, ADB, Appium, a headset, or a phone:

```bash
python3 tests/device/jenkins/test_conan_cache_manager.py -v
python3 tests/device/jenkins/test_android_build_workspace.py -v
```

They cover role separation, full-duration role locks, simultaneous Phone/Pico
wrappers, private permissions, `CONAN_HOME` inheritance, immutable seed
copying, exclusive seed mutation locks, selector redaction, and refusal to
adopt the user's default or an unmarked cache. The workspace test also creates
a real temporary Git repository, runs Phone and Pico children concurrently,
makes both mutate identical checkout-relative Android paths, and proves that
the two resolved checkouts, Gradle homes, Conan homes, and APK exports do not
collide while the original repository remains unchanged.
