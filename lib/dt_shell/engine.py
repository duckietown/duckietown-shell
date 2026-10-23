"""Engine-specific grants and private Docker/source handoffs over the DTS broker."""

import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sys

import dt_shell_device

from .engine_runtime import (
    EngineAuthorizationError, EngineGrantExpired, PROOF_AUDIENCE,
    native_trust, validate_context, validate_grant,
)
from .exceptions import UserError
from .renderer import (
    RendererGrantExpired, RendererHubUnavailable, RendererSession, _canonical,
)


def _trust():
    try:
        return native_trust()
    except (ImportError, RuntimeError) as error:
        raise UserError(
            "Engine authorization requires the coordinated Engine-enabled native DTS release. "
            "Update DTS and its signed commands together."
        ) from error


def new_context(*, runtime: str, image: str, development=False) -> dict:
    return {
        "distribution": "ente", "runtime": runtime, "image": image,
        "device_id": dt_shell_device.get_device_id(), "development": development,
    }


class EngineSession(RendererSession):
    label = "Engine"
    cache_namespace = "engine"
    route_prefix = "engine"
    bind_host = "0.0.0.0"
    hub_endpoint = "/api/v1/auth/token/engine/"
    maintenance_interval = 10

    def __init__(self, shell, *, context: dict, renew=False):
        try:
            validate_context(context)
        except EngineAuthorizationError as error:
            raise UserError(str(error)) from error
        self.context = context
        self.secret = secrets.token_hex(32)
        super().__init__(
            shell, os_family={"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform],
            release=context, development=context["development"], renew=renew,
        )

    def _profile_required(self):
        distro = getattr(getattr(self.shell.profile, "distro", None), "name", None)
        if distro not in ("ente", "ente-staging"):
            raise UserError("Duckiematrix is exclusive to Ente. Select an Ente DTS profile.")

    def _trusted_keys(self):
        return _trust()

    def _broker_headers(self):
        return {**super()._broker_headers(), "Authorization": "Bearer " + self.secret}

    def _broker_allowed(self, headers):
        value = headers.get("Authorization", "")
        return value.isascii() and hmac.compare_digest(value, "Bearer " + self.secret)

    def _broker_challenge(self, challenge):
        return {"challenge": challenge, "consumer": "engine"}

    def _handle_challenge(self, request):
        if (
            not isinstance(request, dict) or set(request) != {"challenge", "consumer"}
            or request["consumer"] != "engine"
        ):
            raise UserError("The Engine challenge has an invalid consumer or structure.")
        return self.proof(request["challenge"], consumer="engine")

    def _validate(self, grant):
        try:
            return validate_grant(
                grant, issuer_keys=self.issuer_keys, development=self.development,
                expected={
                    "issuer": self.issuer, "uid": self.uid, "identity_sha256": self.identity_sha256,
                    "device_id": self.parameters["device_id"], "launch_key": self.launch_key,
                },
            )
        except EngineGrantExpired as error:
            raise RendererGrantExpired(str(error)) from error
        except EngineAuthorizationError as error:
            if hasattr(self, "grant_path"):
                self.grant_path.unlink(missing_ok=True)
            raise UserError(str(error)) from error

    def _request(self):
        try:
            return super()._request()
        except RendererHubUnavailable:
            raise
        except UserError:
            self.grant_path.unlink(missing_ok=True)
            raise

    def _proof_claims(self, challenge, now, consumer):
        if consumer != "engine" or self.context["device_id"] != self.parameters["device_id"]:
            raise UserError("Engine proofs require the Engine consumer and the launching DTS computer.")
        return {
            "format": 1, "audience": PROOF_AUDIENCE,
            "session_id": self.session_id, "challenge": challenge,
            "grant_sha256": hashlib.sha256(self.grant.encode("ascii")).hexdigest(),
            "uid": self.uid, "identity_sha256": self.identity_sha256,
            "device_id": self.parameters["device_id"], "consumer": consumer,
            "context": self.context, "issued_at": int(now),
            "expires_at": min(int(now) + 30, self.claims["expires_at"]),
        }

    def handoff(self, *, broker_host="127.0.0.1") -> dict:
        if not isinstance(broker_host, str) or not broker_host or any(
            character in broker_host for character in ("/", "\\", "@", "?", "#", "\x00")
        ):
            raise UserError("Invalid Engine broker host.")
        host = f"[{broker_host}]" if ":" in broker_host else broker_host
        return {
            "format": 1, "broker": f"http://{host}:{self.server.server_port}{self.path}",
            "secret": self.secret, "session_id": self.session_id,
            "consumer": "engine", "context": self.context,
        }

    def write_handoff(self, destination: Path, *, broker_host="127.0.0.1") -> os.stat_result:
        content = _canonical(self.handoff(broker_host=broker_host))
        try:
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                return os.fstat(stream.fileno())
        except OSError as error:
            raise UserError(f"Cannot write a new private Engine handoff at '{destination}': {error}") from error
