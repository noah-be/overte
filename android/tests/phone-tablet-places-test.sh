#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
places="$repo_root/scripts/system/places/places.js"
qml="$repo_root/scripts/system/places/PicoPlaces.qml"

require() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$places" 'useQmlApp[[:space:]]*=[[:space:]]*!PlatformInfo[.]has3DHTML\(\)' \
    'Phone Places selects its local QML application'
require "$places" 'qmlEventsConnected[[:space:]]*=[[:space:]]*false' \
    'Places tracks its QML bridge lifecycle'
require "$places" 'if[[:space:]]*\(!qmlEventsConnected\)' \
    'Places prevents duplicate QML bridge connections'
require "$places" 'disconnectQmlEvents\(\);' \
    'Places disconnects its QML bridge when leaving the app'
require "$places" 'disconnectWebEvents\(\);' \
    'Places also releases its desktop web bridge on external navigation'
require "$places" 'try[[:space:]]*\{[[:space:]]*$' \
    'Places guards untrusted JSON and network operations'
require "$places" 'function validUiAddress\(value\)' \
    'Places validates local QML navigation payloads before dereferencing them'
require "$places" 'typeof value === "string" && value[.]length > 0' \
    'Places rejects missing and non-string QML navigation destinations'
require "$places" 'value[.]length <= MAX_UI_ADDRESS_LENGTH' \
    'Places bounds QML navigation destination length'
require "$places" '\\u0000-\\u001f\\u007f' \
    'Places rejects control characters in QML navigation destinations'
require "$places" 'if[[:space:]]*\(validUiAddress\(messageObj[.]address\)\)' \
    'Places teleports only after validating the QML address'
require "$places" 'if[[:space:]]*\(!validUiAddress\(messageObj[.]address\)\)' \
    'Places refuses to broadcast portals with invalid destinations'
if grep -Eq 'PICO_PLACES_TELEPORT|print\([^)]*(messageObj[.]address|messageObj[.]name)' "$places"; then
    printf 'FAIL: Places logs a user destination or place name\n' >&2
    exit 1
fi
printf 'PASS: Places does not log user destinations or place names\n'
require "$places" 'httpRequest[.]status[[:space:]]*<[[:space:]]*200' \
    'Places rejects unsuccessful HTTP responses'
require "$places" 'finally[[:space:]]*\{' \
    'Places releases request state after success or failure'
require "$places" 'function abortActiveRequest\(\)' \
    'Places centralizes pending-request cancellation'
require "$places" 'appStatus[[:space:]]*=[[:space:]]*false;[[:space:]]*$' \
    'Places tracks when external navigation closes the app'
require "$places" 'abortActiveRequest\(\);' \
    'Places aborts a pending request when the app closes'
require "$places" 'shuttingDown[[:space:]]*\|\|[[:space:]]*!appStatus' \
    'Places does not deliver request results after its tablet app closes'
require "$places" 'Array[.]isArray\(placesData[.]data[.]places\)' \
    'Places validates the server response shape before processing it'
require "$places" '!places\[i\][[:space:]]*\|\|[[:space:]]*!places\[i\][.]domain' \
    'Places skips malformed individual directory entries'
require "$places" '!instruction[[:space:]]*\|\|[[:space:]]*typeof instruction !== "object"' \
    'Places rejects malformed portal-channel payloads'
require "$places" 'function validPortalPosition\(value\)' \
    'Places centralizes portal position validation'
require "$places" 'typeof value[.]x === "number" && isFinite\(value[.]x\)' \
    'Places requires finite numeric portal coordinates'
require "$places" 'validPortalPosition\(instruction[.]position\).*&&' \
    'Places validates received portal positions before Vec3 operations'
require "$places" 'validUiAddress\(instruction[.]url\)' \
    'Places validates received portal destinations before entity creation'
require "$places" 'rezzerPortalCount < MAX_REZZED_PORTAL' \
    'Places enforces its portal limit without an off-by-one overflow'
require "$places" 'rezzedPortalTimers\[portalID\][[:space:]]*=[[:space:]]*cleanupTimer' \
    'Places owns every portal expiry timer'
require "$places" 'function clearRezzedPortals\(\)' \
    'Places centralizes portal timer and entity teardown'
require "$places" 'Script[.]clearTimeout\(rezzedPortalTimers\[portalID\]\)' \
    'Places cancels portal expiry callbacks at shutdown'
require "$places" 'clearRezzedPortals\(\);' \
    'Places removes live local portals during script cleanup'
require "$places" 'if[[:space:]]*\(!isAndroidPhone\)' \
    'Phone Places avoids mutable tablet-button proxy updates'
require "$qml" 'height:[[:space:]]*Math[.]max\(82,' \
    'Places list entries expose touch-sized delegates'
require "$qml" 'ScrollBar[.]vertical:[[:space:]]*ScrollBar' \
    'Places exposes scroll position for long result lists'

printf 'Phone tablet Places checks passed.\n'
