#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output="$(mktemp -d "${TMPDIR:-/tmp}/overte-user-story-policy.XXXXXXXX")"
trap 'rm -rf -- "$output"' EXIT

javac -d "$output" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/HifiUtils.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyAdapterPositionPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyDomainLocationPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyUserPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyCrashDumpPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/LegacyLatestRequestGate.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryRetrievalCoordinator.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/LegacyLatestRequestGateStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/UserStoryRetrievalCoordinatorStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAdapterPositionPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyDomainLocationPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyUserPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyCrashDumpPolicyStandaloneTest.java"
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.UserStoryDomainPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.LegacyLatestRequestGateStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.UserStoryRetrievalCoordinatorStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAssetTextPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAdapterPositionPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyDomainLocationPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyUserPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyCrashDumpPolicyStandaloneTest

if grep -Eq 'Log\.[A-Za-z]+\([^;]*accessToken|accessToken[^;]*Log\.' \
        "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/fragment/FriendsFragment.java"; then
    printf 'FAIL: legacy Friends UI must not log its access token\n' >&2
    exit 1
fi

main_activity="$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/MainActivity.java"
grep -Fq 'if (LegacyUserPolicy.hasText(username))' "$main_activity" || {
    printf 'FAIL: legacy profile header must validate nullable usernames\n' >&2
    exit 1
}
if grep -Fq 'username.isEmpty()' "$main_activity"; then
    printf 'FAIL: legacy profile header directly dereferences a nullable username\n' >&2
    exit 1
fi

provider="$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryDomainProvider.java"
grep -Fq 'long requestTicket = requestGate.begin();' "$provider" || {
    printf 'FAIL: legacy Places requests do not establish a latest-request ticket\n' >&2
    exit 1
}
grep -Fq 'forceRefresh || requestInFlight' "$provider" || {
    printf 'FAIL: the latest Places request can be starved behind an older request\n' >&2
    exit 1
}
[[ "$(grep -Fc 'requestGate.isCurrent(requestTicket)' "$provider")" -ge 3 ]] || {
    printf 'FAIL: legacy Places completions are not gated before mutation\n' >&2
    exit 1
}

user_list_adapter="$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/view/UserListAdapter.java"
grep -Fq 'long requestTicket = requestGate.begin();' "$user_list_adapter" || {
    printf 'FAIL: legacy People requests do not establish a latest-request ticket\n' >&2
    exit 1
}
[[ "$(grep -Fc 'requestGate.isCurrent(requestTicket)' "$user_list_adapter")" -eq 2 ]] || {
    printf 'FAIL: legacy People completion guards are incomplete\n' >&2
    exit 1
}
python3 - "$user_list_adapter" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
success = source.index("public void retrieveOk(List<User> users)")
success_guard = source.index("requestGate.isCurrent(requestTicket)", success)
success_mutation = source.index("mUsers = new ArrayList<>(users)", success)
failure = source.index("public void retrieveError(Exception e, String message)")
failure_guard = source.index("requestGate.isCurrent(requestTicket)", failure)
failure_mutation = source.index("mAdapterListener.onError", failure)
if not success < success_guard < success_mutation < failure < failure_guard < failure_mutation:
    raise SystemExit("FAIL: legacy People completion guards run after observable mutation")
PY

python3 - "$main_activity" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
header = source.index("private void updateProfileHeader(String username)")
ticket = source.index("profileImageRequestGate.begin()", header)
cancel = source.index("Picasso.get().cancelRequest(mProfilePicture)", header)
validity = source.index("LegacyUserPolicy.hasText(username)", header)
execute = source.index("updateProfilePicture(username, requestTicket)", header)
download = source.index("private void updateProfilePicture(String username, long requestTicket)")
download_guard = source.index("profileImageRequestGate.isCurrent(requestTicket)", download)
picasso_load = source.index("Picasso.get().load(url)", download)
callback = source.index("private class RoundProfilePictureCallback")
success = source.index("public void onSuccess()", callback)
success_guard = source.index("profileImageRequestGate.isCurrent(requestTicket)", success)
success_mutation = source.index("mProfilePicture.getDrawable()", success)
failure = source.index("public void onError(Exception e)", callback)
failure_guard = source.index("profileImageRequestGate.isCurrent(requestTicket)", failure)
failure_mutation = source.index("mProfilePicture.setImageResource", failure)
if not header < ticket < cancel < validity < execute < download < download_guard < picasso_load:
    raise SystemExit("FAIL: legacy profile lookup can outlive a newer username")
if "new RoundProfilePictureCallback(requestTicket)" not in source:
    raise SystemExit("FAIL: the profile image callback does not retain its request ticket")
if not callback < success < success_guard < success_mutation < failure < failure_guard < failure_mutation:
    raise SystemExit("FAIL: stale profile image callbacks can still mutate the ImageView")
PY
