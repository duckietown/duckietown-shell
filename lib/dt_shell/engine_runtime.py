"""Native Duckiematrix Engine permissions, release verification and lifetime guard."""

import hashlib
import logging
import os
from pathlib import Path
import re
import signal
import threading
import time
from urllib.parse import urlsplit

if __package__ == "dt_shell":
    from . import viewer_runtime as runtime
else:
    import duckietown_engine_guard_common as runtime


AUDIENCE = "duckiematrix-engine"
PROOF_AUDIENCE = "duckiematrix-engine-session"
MANIFEST = "duckiematrix-engine.release.json"
HANDOFF_ENV = "DT_MATRIX_ENGINE_HANDOFF"
CONTEXT_FIELDS = {"distribution", "runtime", "image", "device_id", "development"}
EngineAuthorizationError = runtime.ViewerAuthorizationError
EngineGrantExpired = runtime.ViewerGrantExpired
EngineBrokerUnavailable = runtime.ViewerBrokerUnavailable
logger = logging.getLogger(__name__)
_active = None


def native_trust() -> tuple[str, dict[str, str]]:
    if __name__ == "duckietown_engine_guard":
        from duckietown_engine_guard_trust import trust
    else:
        from dt_shell_release import engine_trust as trust
    release, issuers = trust()
    if (
        not runtime.is_digest(release) or not isinstance(issuers, dict)
        or set(issuers) != set(runtime.ISSUERS)
        or any(not runtime.is_digest(key) for key in issuers.values())
        or len({release, *issuers.values()}) != 3
    ):
        raise EngineAuthorizationError("The native Duckiematrix Engine trust configuration is invalid.")
    return release, issuers


def validate_grant(token: str, *, issuer_keys, development: bool, expected=None, now=None) -> dict:
    return runtime.validate_grant(
        token, issuer_keys=issuer_keys, app=None, development=development,
        expected=expected, now=now, audience=AUDIENCE,
    )


def validate_context(context: dict) -> None:
    if (
        not isinstance(context, dict) or set(context) != CONTEXT_FIELDS
        or context["distribution"] != "ente"
        or type(context["development"]) is not bool
        or any(not runtime.is_digest(context[name]) for name in ("runtime", "image", "device_id"))
    ):
        raise EngineAuthorizationError("The signed Duckiematrix Engine launch context is invalid.")


def validate_proof(
    response: dict, *, issuer_keys, challenge: str, session_id: str,
    consumer: str, context: dict, device_id=None, now=None,
) -> dict:
    validate_context(context)
    if consumer != "engine" or not isinstance(response, dict) or set(response) != {"grant", "proof"}:
        raise EngineAuthorizationError("DTS returned an invalid Engine proof or consumer.")
    now = time.time() if now is None else now
    grant = validate_grant(
        response["grant"], issuer_keys=issuer_keys,
        development=context["development"], now=now,
        expected={"device_id": context["device_id"]},
    )
    claims, content, signature = runtime.envelope(runtime.canonical(response["proof"]))
    runtime.verify_signature(grant["launch_key"], content, signature)
    if (
        set(claims) != runtime.PROOF_FIELDS
        or type(claims["format"]) is not int or claims["format"] != 1
        or claims["audience"] != PROOF_AUDIENCE or claims["session_id"] != session_id
        or not isinstance(session_id, str) or re.fullmatch("[0-9a-f]{32}", session_id) is None
        or claims["challenge"] != challenge or claims["consumer"] != "engine"
        or claims["context"] != context
        or claims["grant_sha256"] != hashlib.sha256(response["grant"].encode("ascii")).hexdigest()
        or any(claims[name] != grant[name] for name in ("uid", "identity_sha256", "device_id"))
        or type(claims["issued_at"]) is not int or type(claims["expires_at"]) is not int
        or claims["issued_at"] > now + 5 or claims["issued_at"] < now - 30
        or claims["issued_at"] < grant["issued_at"]
        or not 0 < claims["expires_at"] - claims["issued_at"] <= 30
        or claims["expires_at"] > grant["expires_at"] or claims["expires_at"] <= now
        or (device_id is not None and context["device_id"] != device_id)
    ):
        raise EngineAuthorizationError("The Engine proof is stale, replayed or bound to a different launch.")
    return claims


def read_handoff(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            raise EngineAuthorizationError("Engine handoffs must be regular private files.")
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise EngineAuthorizationError("The Engine handoff must not be group/world accessible.")
        with path.open("rb") as stream:
            data = runtime.decode_json(stream.read(65537), 65536)
    except OSError as error:
        raise EngineAuthorizationError("Cannot read the private Engine handoff. Launch through DTS.") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"format", "broker", "secret", "session_id", "consumer", "context"}
        or type(data["format"]) is not int or data["format"] != 1
        or data["consumer"] != "engine" or not runtime.is_digest(data["secret"])
        or not isinstance(data["session_id"], str) or re.fullmatch("[0-9a-f]{32}", data["session_id"]) is None
        or not isinstance(data["broker"], str)
    ):
        raise EngineAuthorizationError("The Engine handoff is malformed.")
    validate_context(data["context"])
    broker = urlsplit(data["broker"])
    try:
        valid = (
            broker.scheme == "http" and broker.hostname is not None and broker.port is not None
            and broker.path == f"/engine/{data['session_id']}/proof"
            and broker.username is None and broker.password is None and not broker.query and not broker.fragment
        )
    except ValueError as error:
        raise EngineAuthorizationError("The Engine broker address is invalid.") from error
    if not valid:
        raise EngineAuthorizationError("The Engine broker is not a paired DTS session.")
    return data


class EngineLease(runtime.ViewerLease):
    label = "Duckiematrix Engine"

    def _validate_response(self, response, **parameters):
        return validate_proof(response, **parameters)


def verify_release(root: Path, *, release_key: str, issuer_keys) -> dict:
    release = runtime.verify_release(
        root, release_key=release_key, issuer_keys=issuer_keys, kind="engine",
        manifest=MANIFEST, audience="duckiematrix-engine-release",
    )
    if (
        release["platform"] not in ("linux", "linux-arm64")
        or release["entrypoint"] != "packages/duckiematrix_engine"
        or any(
            re.fullmatch(
                r"packages/duckiematrix_engine/(?:__pycache__/)?(?:bootstrap|engine)(?:\.[^/]+)?\.(?:py|pyc|pyo)",
                path,
            )
            for path in release["files"]
        )
        or any(
            not any(
                re.fullmatch(r"packages/duckiematrix_engine/" + name + r"\.[^/]+\.so", path)
                for path in release["files"]
            )
            for name in ("bootstrap", "engine")
        )
    ):
        raise EngineAuthorizationError("The production Engine requires its compiled bootstrap and core without source fallbacks.")
    return release


def verify_image_catalog(raw: bytes, *, release_key: str) -> dict:
    return runtime.verify_backend_catalog(
        raw, release_key=release_key, audience="duckiematrix-engine-images",
        repository="dt-duckiematrix",
    )


class EngineAuthorization:
    def __init__(self, lease: EngineLease, root: Path):
        self.lease = lease
        self.root = root.resolve()
        self.error = None
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._watch, name="engine-authorization", daemon=True)
        self.thread.start()

    def current(self) -> None:
        if self.closed.is_set() or self.error is not None:
            raise EngineAuthorizationError(self.error or "The Engine authorization session is closed.")
        self.lease.current()

    def _terminate(self, message: str) -> None:
        self.error = message
        logger.error("Duckiematrix Engine authorization ended: %s", message)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except OSError:
            logger.exception("Cannot request Engine shutdown.")
            os._exit(1)
        if not self.closed.wait(5):
            logger.error("The Engine did not finish shutting down after authorization ended.")
            os._exit(1)

    def _watch(self) -> None:
        try:
            while not self.closed.wait(1):
                self.lease.current()
                if self.lease.deadline - time.monotonic() <= 20:
                    try:
                        self.lease.renew()
                    except EngineBrokerUnavailable as error:
                        logger.warning("%s", error)
                        self.lease.current()
        except EngineAuthorizationError as error:
            self._terminate(str(error))
        finally:
            if not self.closed.is_set() and self.error is None:
                self._terminate("The Engine authorization monitor stopped unexpectedly.")

    def close(self) -> None:
        global _active
        self.closed.set()
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=5)
        if _active is self:
            _active = None


def authorize_engine(root: Path) -> EngineAuthorization:
    global _active
    if _active is not None:
        current_authorization(root)
        return _active
    path = os.environ.get(HANDOFF_ENV)
    if not path:
        raise EngineAuthorizationError(
            "The Duckiematrix Engine requires a live authorized DTS session. "
            "Use 'dts matrix engine run'; source work requires Engine developer authorization."
        )
    handoff = read_handoff(Path(path))
    release_key, issuer_keys = native_trust()
    if not handoff["context"]["development"]:
        release = verify_release(root, release_key=release_key, issuer_keys=issuer_keys)
        if release["sha256"] != handoff["context"]["runtime"]:
            raise EngineAuthorizationError("The Engine payload does not match this authorized launch.")
    lease = EngineLease(handoff, issuer_keys=issuer_keys)
    _active = EngineAuthorization(lease, root)
    return _active


def current_authorization(root: Path) -> None:
    if _active is None or _active.root != root.resolve():
        raise EngineAuthorizationError("Initialize the Engine through its authorized DTS bootstrap.")
    _active.current()
