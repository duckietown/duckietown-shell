"""Viewer-specific grants and handoffs over the shared native DTS session broker."""

import hashlib
import hmac
from pathlib import Path
import secrets
import os
import platform
import sys

import dt_shell_device

from .exceptions import UserError
from .renderer import (
    RendererGrantExpired, RendererHubUnavailable, RendererSession, _canonical, _private_write,
)
from .viewer_runtime import (
    APPS, PROOF_AUDIENCE, ViewerAuthorizationError, ViewerGrantExpired,
    ViewerLease, native_trust, read_handoff, validate_context, validate_grant, verify_release,
)

FORWARDED_HANDOFF_ENV = "DTS_VIEWER_HANDOFF"
COMMAND_APPS = {
    "duckiebot.image_viewer": "image_viewer",
    "duckiebot.keyboard_control": "keyboard_controller",
    "duckiebot.calibrate_intrinsics": "intrinsics_calibrator",
    "duckiebot.calibrate_extrinsics": "extrinsics_calibrator",
    "duckiebot.led_control": "led_controller",
    "duckiebot.graph_plotter": "graph_plotter",
}


def host_info():
    release, issuers = _trust()
    return {
        "format": 1, "device_id": dt_shell_device.get_device_id(),
        "platform": {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform],
        "architecture": platform.machine().lower(), "trust": {"release": release, "issuers": issuers},
    }


def forwarded_lease(app: str):
    path = os.environ.get(FORWARDED_HANDOFF_ENV)
    if not path:
        return None
    _, issuers = _trust()
    try:
        handoff = read_handoff(Path(path))
        if handoff["consumer"] != "desktop" or handoff["context"]["app"] != app:
            raise ViewerAuthorizationError("The delegated handoff belongs to a different app or consumer.")
        return ViewerLease(handoff, issuer_keys=issuers, device_id=dt_shell_device.get_device_id())
    except (ViewerAuthorizationError, dt_shell_device.DeviceIdentityError) as error:
        raise UserError(str(error)) from error


def new_context(*, app: str, endpoint: str, backend: str, backend_image: str, desktop, desktop_device: str, development=False, desktop_version=None):
    tickets = {role: secrets.token_hex(32) for role in ("browser", "desktop", "ready")}
    context = {
        "app": app, "distribution": "ente", "endpoint": endpoint,
        "backend": backend, "backend_image": backend_image, "desktop": desktop, "desktop_version": desktop_version,
        "devices": {"backend": dt_shell_device.get_device_id(), "desktop": desktop_device},
        "tickets": {role: hashlib.sha256(value.encode("ascii")).hexdigest() for role, value in tickets.items()},
        "development": development,
    }
    return context, tickets


def authorize_install(shell, app="empty_viewer", *, development=False):
    forwarded = forwarded_lease(app)
    if forwarded is not None:
        if development and not forwarded.handoff["context"]["development"]:
            raise UserError("Viewer development requires a separate staff or superuser developer permission.")
        return
    context, _ = new_context(
        app=app, endpoint="http://127.0.0.1:1/app/", backend="0" * 64, backend_image="0" * 64,
        desktop=None, desktop_device=dt_shell_device.get_device_id(),
        development=development,
    )
    session = ViewerSession(shell, app=app, context=context, os_family=host_info()["platform"])
    session.close()


def _trust():
    try:
        return native_trust()
    except (ImportError, RuntimeError) as error:
        raise UserError(
            "Viewer authorization requires the updated official native DTS runtime. "
            "Install the coordinated Viewer-enabled DTS release."
        ) from error


def verify_viewer_release(directory: Path) -> dict:
    release_key, issuer_keys = _trust()
    try:
        return verify_release(directory, release_key=release_key, issuer_keys=issuer_keys)
    except ViewerAuthorizationError as error:
        raise UserError(str(error)) from error


class ViewerSession(RendererSession):
    label = "Viewer"
    cache_namespace = "viewer"
    route_prefix = "viewer"
    bind_host = "0.0.0.0"
    hub_endpoint = "/api/v1/auth/token/viewer/"
    maintenance_interval = 10

    def __init__(self, shell, *, app: str, context: dict, os_family: str, renew=False):
        try:
            validate_context(context)
        except ViewerAuthorizationError as error:
            raise UserError(str(error)) from error
        if app not in APPS or context["app"] != app:
            raise UserError("Unknown or mismatched Viewer app.")
        self.app = app
        self.context = context
        self.secret = secrets.token_hex(32)
        super().__init__(
            shell, os_family=os_family, release=context,
            development=context["development"], renew=renew,
        )

    def _profile_required(self):
        distro = getattr(getattr(self.shell.profile, "distro", None), "name", None)
        if distro not in ("ente", "ente-staging"):
            raise UserError("Protected Viewer sessions require an Ente profile. Daffy uses its legacy Viewer channel.")

    def _trusted_keys(self):
        return _trust()

    def _cache_variant(self):
        return "-" + self.app

    def _request_parameters(self):
        return {**super()._request_parameters(), "app": self.app}

    def _broker_headers(self):
        return {**super()._broker_headers(), "Authorization": "Bearer " + self.secret}

    def _broker_allowed(self, headers):
        value = headers.get("Authorization", "")
        return value.isascii() and hmac.compare_digest(value, "Bearer " + self.secret)

    def _broker_challenge(self, challenge):
        return {"challenge": challenge, "consumer": "backend"}

    def _handle_challenge(self, request):
        if (
            not isinstance(request, dict) or set(request) != {"challenge", "consumer"}
            or request["consumer"] not in ("backend", "desktop")
        ):
            raise UserError("The Viewer challenge has an invalid consumer or structure.")
        return self.proof(request["challenge"], consumer=request["consumer"])

    def _validate(self, grant):
        try:
            return validate_grant(
                grant, issuer_keys=self.issuer_keys, app=self.app, development=self.development,
                expected={
                    "issuer": self.issuer, "uid": self.uid,
                    "identity_sha256": self.identity_sha256,
                    "device_id": self.parameters["device_id"], "launch_key": self.launch_key,
                },
            )
        except ViewerGrantExpired as error:
            raise RendererGrantExpired(str(error)) from error
        except ViewerAuthorizationError as error:
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
        if consumer not in ("backend", "desktop"):
            raise UserError("Viewer proofs require a specific consumer role.")
        return {
            "format": 1, "audience": PROOF_AUDIENCE,
            "session_id": self.session_id, "challenge": challenge,
            "grant_sha256": hashlib.sha256(self.grant.encode("ascii")).hexdigest(),
            "uid": self.uid, "identity_sha256": self.identity_sha256,
            "device_id": self.parameters["device_id"], "consumer": consumer,
            "context": self.context, "issued_at": int(now),
            "expires_at": min(int(now) + 30, self.claims["expires_at"]),
        }

    def write_handoff(self, destination: Path, *, consumer: str, ticket: str, broker_host="127.0.0.1"):
        if consumer not in ("backend", "desktop"):
            raise UserError("Unknown Viewer consumer role.")
        _private_write(
            Path(destination),
            _canonical({
                "format": 1,
                "broker": f"http://{broker_host}:{self.server.server_port}{self.path}",
                "secret": self.secret, "session_id": self.session_id,
                "consumer": consumer, "context": self.context, "ticket": ticket,
            }),
        )
