"""Bounded commands for the independent assignment-owned shared entity."""
import secrets
import threading
import re

ENTITY = "OVERTE_E2E_SHARED_COLOR"
ACTOR = "OVERTE_E2E_ACTOR_FIXTURE"
SESSION = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")


class CollaborationBroker:
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = None
        self.committed = None

    def reset(self):
        with self.lock:
            self.pending = None
            self.committed = None

    def submit(self, payload):
        if (not isinstance(payload, dict)
                or set(payload) != {"schemaVersion", "entityName", "value"}
                or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1
                or payload["entityName"] != ENTITY or payload["value"] not in ("blue", "orange")):
            raise ValueError("invalid controlled collaboration command")
        with self.lock:
            if self.committed is None or self.pending is not None:
                raise RuntimeError("independent actor is not ready for another edit")
            if self.committed["revision"] >= 2**53 - 1:
                raise RuntimeError("controlled collaboration revision is exhausted")
            self.pending = {**payload, "commandId": secrets.token_hex(16),
                            "actorSessionId": self.committed["actorSessionId"],
                            "revision": self.committed["revision"] + 1}
            return dict(self.pending)

    def command(self):
        with self.lock:
            return dict(self.pending) if self.pending else {"schemaVersion": 1, "pending": False}

    def state(self):
        with self.lock:
            if self.committed is None or self.pending is not None:
                raise RuntimeError("independent actor has not seeded its entity")
            return dict(self.committed)

    def report(self, payload):
        fields = {"schemaVersion", "commandId", "entityName", "value", "revision", "actorId", "actorSessionId"}
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1
                or payload["entityName"] != ENTITY or payload["actorId"] != ACTOR
                or not isinstance(payload["actorSessionId"], str)
                or not SESSION.fullmatch(payload["actorSessionId"])
                or payload["actorSessionId"] == "00000000-0000-0000-0000-000000000000"
                or type(payload["revision"]) is not int or not 0 <= payload["revision"] <= 2**53 - 1
                or payload["value"] not in ("blue", "orange")):
            raise ValueError("invalid independent actor observation")
        with self.lock:
            if payload["commandId"] == "seed" and payload["revision"] == 0 and payload["value"] == "blue":
                if self.pending is not None or self.committed is not None and self.committed != payload:
                    raise ValueError("actor restarted outside a controlled fixture reset")
            elif self.pending is None or payload != {**self.pending, "actorId": ACTOR}:
                # A repeated acknowledgment is harmless, but cannot create a
                # second revision or acknowledge a different command.
                if payload == self.committed:
                    return
                raise ValueError("actor did not observe the exact pending mutation")
            self.committed = dict(payload)
            self.pending = None
