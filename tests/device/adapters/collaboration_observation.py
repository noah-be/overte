"""Join real client entity properties to the independent native actor session."""
import math
import re

ENTITY = "OVERTE_E2E_SHARED_COLOR"
ACTOR = "OVERTE_E2E_ACTOR_FIXTURE"
SESSION = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
PORTABLE_FIELDS = {"schemaVersion", "entityName", "actorId", "revision", "value"}
NATIVE_FIELDS = PORTABLE_FIELDS | {"actorSessionId"}


def native_state(value):
    if (not isinstance(value, dict) or set(value) != NATIVE_FIELDS
            or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["entityName"] != ENTITY or value["actorId"] != ACTOR
            or type(value["revision"]) is not int or not 0 <= value["revision"] <= 9007199254740991
            or value["value"] not in ("blue", "orange")
            or not isinstance(value["actorSessionId"], str)
            or not SESSION.fullmatch(value["actorSessionId"])
            or value["actorSessionId"] == "00000000-0000-0000-0000-000000000000"):
        raise ValueError("invalid native collaboration state")
    return value


def actor_receipt(value):
    if not isinstance(value, dict) or set(value) != NATIVE_FIELDS | {"commandId"}:
        raise ValueError("invalid independent actor receipt")
    command = value["commandId"]
    if not isinstance(command, str) or not (command == "seed" or re.fullmatch(r"[0-9a-f]{32}", command)):
        raise ValueError("invalid independent actor command identity")
    native_state({key: value[key] for key in NATIVE_FIELDS})
    if (command == "seed") != (value["revision"] == 0):
        raise ValueError("independent actor command and revision disagree")
    return value


def portable_observation(envelope, actor, now_ms, probe):
    fields = {"schemaVersion", "sampleEpochMs", "sampleSequence", "entityCount", "observation"}
    if (not isinstance(envelope, dict) or set(envelope) != fields
            or type(envelope["schemaVersion"]) is not int or envelope["schemaVersion"] != 1
            or type(envelope["entityCount"]) is not int or envelope["entityCount"] != 1
            or type(envelope["sampleSequence"]) is not int or envelope["sampleSequence"] <= 0
            or not isinstance(envelope["sampleEpochMs"], (int, float))
            or isinstance(envelope["sampleEpochMs"], bool)
            or not math.isfinite(envelope["sampleEpochMs"])
            or not 0 <= now_ms - envelope["sampleEpochMs"] <= 5000
            # The private observation is written immediately before its root
            # snapshot. Reject evidence predating the current process's probe.
            or envelope["sampleSequence"] < probe["sampleSequence"] - 1
            or envelope["sampleEpochMs"] < probe["sampleEpochMs"] - 750):
        raise ValueError("collaboration observation is stale, ambiguous or malformed")
    observed = native_state(envelope["observation"])
    expected = actor_receipt(actor)
    if any(observed[key] != expected[key] for key in NATIVE_FIELDS):
        raise ValueError("client entity does not match the independent native author and revision")
    return {key: observed[key] for key in PORTABLE_FIELDS}
