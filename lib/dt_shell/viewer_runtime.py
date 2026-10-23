"""Shared native Viewer verification, used by DTS, Docker and the desktop sidecar."""

import argparse
import base64
import binascii
import datetime
import hashlib
import http.client
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import sys
import tempfile
import time
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


APPS = (
    "image_viewer", "keyboard_controller", "intrinsics_calibrator",
    "extrinsics_calibrator", "led_controller", "graph_plotter",
    "empty_viewer", "form_generator",
)
ISSUERS = ("https://hub.duckietown.com", "https://staging-hub.duckietown.com")
AUDIENCE = "duckietown-viewer"
PROOF_AUDIENCE = "duckietown-viewer-session"
MANIFEST = "duckietown-viewer.release.json"
GRACE_END = int(datetime.datetime(2027, 2, 1, tzinfo=datetime.timezone.utc).timestamp())
GRANT_FIELDS = {
    "format", "audience", "capability", "issuer", "uid", "identity_sha256",
    "device_id", "launch_key", "is_staff", "is_superuser", "base_plan",
    "entitlement_expiration", "issued_at", "expires_at", "renewable", "app", "distribution",
}
CONTEXT_FIELDS = {
    "app", "distribution", "endpoint", "backend", "backend_image", "desktop", "desktop_version", "devices",
    "tickets", "development",
}
PROOF_FIELDS = {
    "format", "audience", "session_id", "challenge", "grant_sha256", "uid",
    "identity_sha256", "device_id", "issued_at", "expires_at", "consumer", "context",
}


class ViewerAuthorizationError(RuntimeError):
    pass


class ViewerGrantExpired(ViewerAuthorizationError):
    pass


class ViewerBrokerUnavailable(ViewerAuthorizationError):
    pass


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ViewerAuthorizationError("Viewer authorization contains duplicate JSON fields.")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ViewerAuthorizationError("Viewer authorization contains non-finite numbers.")


def decode_json(content: bytes, limit: int = 1024 * 1024):
    if len(content) > limit:
        raise ViewerAuthorizationError("Viewer authorization exceeds its size limit.")
    try:
        return json.loads(
            content, object_pairs_hook=_pairs,
            parse_constant=_invalid_constant,
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ViewerAuthorizationError("Viewer authorization is not valid JSON.") from error


def is_digest(value) -> bool:
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def envelope(value: bytes) -> tuple[dict, bytes, bytes]:
    data = decode_json(value)
    if not isinstance(data, dict) or set(data) != {"payload", "signature"}:
        raise ViewerAuthorizationError("Viewer authorization has an invalid signed envelope.")
    try:
        content = base64.b64decode(data["payload"], validate=True)
        signature = base64.b64decode(data["signature"], validate=True)
        claims = decode_json(content)
        if not isinstance(claims, dict) or canonical(claims) != content or len(signature) != 64:
            raise ViewerAuthorizationError("Viewer authorization is not canonical signed JSON.")
    except (ValueError, TypeError, binascii.Error) as error:
        raise ViewerAuthorizationError("Viewer authorization has invalid signature encoding.") from error
    return claims, content, signature


def verify_signature(public: str, content: bytes, signature: bytes) -> None:
    if not is_digest(public):
        raise ViewerAuthorizationError("Viewer verification has an invalid pinned public key.")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(signature, content)
    except InvalidSignature as error:
        raise ViewerAuthorizationError("Viewer signature verification failed.") from error


def native_trust() -> tuple[str, dict[str, str]]:
    if __name__ == "duckietown_viewer_guard":
        from duckietown_viewer_guard_trust import trust
    else:
        from dt_shell_release import viewer_trust as trust
    release, issuers = trust()
    if (
        not is_digest(release) or not isinstance(issuers, dict) or set(issuers) != set(ISSUERS)
        or any(not is_digest(key) for key in issuers.values())
        or len({release, *issuers.values()}) != 3
    ):
        raise ViewerAuthorizationError("The native Viewer trust configuration is invalid.")
    return release, issuers


def validate_grant(
    token: str, *, issuer_keys: dict[str, str], app: str | None, development: bool,
    expected=None, now=None, audience=AUDIENCE,
) -> dict:
    if audience not in (AUDIENCE, "duckiematrix-engine"):
        raise ViewerAuthorizationError("Unknown application authorization audience.")
    fields = GRANT_FIELDS if audience == AUDIENCE else GRANT_FIELDS - {"app", "distribution"}
    if not isinstance(token, str):
        raise ViewerAuthorizationError("Hub did not provide a signed Viewer permission.")
    try:
        encoded = token.encode("ascii")
    except UnicodeError as error:
        raise ViewerAuthorizationError("The signed Viewer permission is not ASCII JSON.") from error
    claims, content, signature = envelope(encoded)
    issuer = claims.get("issuer")
    if not isinstance(issuer, str) or issuer not in ISSUERS or issuer not in issuer_keys:
        raise ViewerAuthorizationError("The Viewer permission has an unapproved issuer.")
    verify_signature(issuer_keys[issuer], content, signature)
    now = time.time() if now is None else now
    if (
        set(claims) not in (fields, fields | {"plan_grace_until"})
        or type(claims["format"]) is not int or claims["format"] != 1
        or claims["audience"] != audience
        or claims["capability"] != ("develop:" if development else "use:") + audience
        or (
            audience == AUDIENCE
            and (app not in APPS or claims["app"] != app or claims["distribution"] != "ente")
        )
        or type(claims["uid"]) is not int or claims["uid"] <= 0
        or any(not is_digest(claims[name]) for name in ("identity_sha256", "device_id", "launch_key"))
        or any(type(claims[name]) is not bool for name in ("is_staff", "is_superuser"))
        or (claims["base_plan"] is not None and not isinstance(claims["base_plan"], str))
        or claims["renewable"] is not False
        or type(claims["issued_at"]) is not int or type(claims["expires_at"]) is not int
        or claims["issued_at"] <= 0 or claims["issued_at"] > now + 5
        or not 0 < claims["expires_at"] - claims["issued_at"] <= (3600 if development else 86400)
    ):
        raise ViewerAuthorizationError("The Viewer permission has invalid scope, app, binding or lifetime.")
    privileged = claims["is_staff"] or claims["is_superuser"]
    grace = claims.get("plan_grace_until")
    if "plan_grace_until" in claims and (
        type(grace) is not int or grace != GRACE_END or claims["expires_at"] > grace
        or privileged or claims["base_plan"] is not None or claims["entitlement_expiration"] is not None
    ):
        raise ViewerAuthorizationError("The Viewer permission has invalid Ente plan grace.")
    if (development and not privileged) or (
        not privileged and grace is None
        and claims["base_plan"] not in ("independent_user", "institutional_user")
    ):
        raise ViewerAuthorizationError("A qualifying plan or Viewer developer permission is required.")
    end = claims["entitlement_expiration"]
    if end is not None and (
        type(end) not in (int, float) or not math.isfinite(end) or end < claims["expires_at"]
    ):
        raise ViewerAuthorizationError("Viewer authorization extends beyond the qualifying plan.")
    if expected is not None and any(claims.get(key) != value for key, value in expected.items()):
        raise ViewerAuthorizationError("The Viewer permission belongs to a different identity, computer or launch.")
    if now >= claims["expires_at"]:
        raise ViewerGrantExpired("The Viewer permission has expired. Relaunch through DTS.")
    return claims


def validate_context(context: dict) -> None:
    if (
        not isinstance(context, dict) or set(context) != CONTEXT_FIELDS
        or context["app"] not in APPS or context["distribution"] != "ente"
        or type(context["development"]) is not bool
        or not isinstance(context["endpoint"], str)
        or not isinstance(context["devices"], dict) or set(context["devices"]) != {"backend", "desktop"}
        or any(not is_digest(value) for value in context["devices"].values())
        or not isinstance(context["tickets"], dict) or set(context["tickets"]) != {"browser", "desktop", "ready"}
        or any(not is_digest(value) for value in context["tickets"].values())
        or not is_digest(context["backend"])
        or not is_digest(context["backend_image"])
        or (context["desktop"] is not None and not is_digest(context["desktop"]))
        or (
            context["desktop"] is not None
            and (not isinstance(context["desktop_version"], str) or re.fullmatch(r"\d+\.\d+\.\d+", context["desktop_version"]) is None)
        )
        or (context["desktop"] is None and context["desktop_version"] is not None)
    ):
        raise ViewerAuthorizationError("The signed Viewer launch context is invalid.")
    endpoint = urlsplit(context["endpoint"])
    try:
        valid = (
            endpoint.scheme == "http" and bool(endpoint.hostname) and endpoint.port is not None
            and endpoint.path == "/app/" and not endpoint.query and not endpoint.fragment
            and endpoint.username is None and endpoint.password is None
            and context["endpoint"] == f"http://{endpoint.netloc}/app/"
        )
    except ValueError as error:
        raise ViewerAuthorizationError("The paired Viewer endpoint is invalid.") from error
    if not valid:
        raise ViewerAuthorizationError("The Viewer launch is not bound to an exact backend endpoint.")


def validate_proof(
    response: dict, *, issuer_keys: dict[str, str], challenge: str, session_id: str,
    consumer: str, context: dict, device_id=None, now=None,
) -> dict:
    validate_context(context)
    if consumer not in ("backend", "desktop"):
        raise ViewerAuthorizationError("The Viewer consumer role is invalid.")
    if not isinstance(response, dict) or set(response) != {"grant", "proof"}:
        raise ViewerAuthorizationError("DTS returned an invalid Viewer proof.")
    now = time.time() if now is None else now
    grant = validate_grant(
        response["grant"], issuer_keys=issuer_keys, app=context["app"],
        development=context["development"], now=now,
    )
    claims, content, signature = envelope(canonical(response["proof"]))
    verify_signature(grant["launch_key"], content, signature)
    if (
        set(claims) != PROOF_FIELDS or type(claims["format"]) is not int or claims["format"] != 1
        or claims["audience"] != PROOF_AUDIENCE or claims["session_id"] != session_id
        or not isinstance(session_id, str) or re.fullmatch("[0-9a-f]{32}", session_id) is None
        or claims["challenge"] != challenge or claims["consumer"] != consumer
        or claims["context"] != context
        or claims["grant_sha256"] != hashlib.sha256(response["grant"].encode("ascii")).hexdigest()
        or any(claims[name] != grant[name] for name in ("uid", "identity_sha256", "device_id"))
        or type(claims["issued_at"]) is not int or type(claims["expires_at"]) is not int
        or claims["issued_at"] > now + 5 or claims["issued_at"] < now - 30
        or claims["issued_at"] < grant["issued_at"]
        or not 0 < claims["expires_at"] - claims["issued_at"] <= 30
        or claims["expires_at"] > grant["expires_at"] or claims["expires_at"] <= now
        or (device_id is not None and context["devices"][consumer] != device_id)
    ):
        raise ViewerAuthorizationError("The Viewer proof is stale, replayed or bound to a different launch.")
    return claims


def read_handoff(path: Path) -> dict:
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ViewerAuthorizationError("Viewer handoffs must be regular private files.")
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ViewerAuthorizationError("The Viewer handoff file must not be group/world accessible.")
        with path.open("rb") as stream:
            data = decode_json(stream.read(65537), 65536)
    except OSError as error:
        raise ViewerAuthorizationError("Cannot read the private Viewer handoff. Launch through DTS.") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"format", "broker", "secret", "session_id", "consumer", "context", "ticket"}
        or type(data["format"]) is not int or data["format"] != 1
        or data["consumer"] not in ("backend", "desktop")
        or not isinstance(data["broker"], str)
        or not is_digest(data["secret"]) or not is_digest(data["ticket"])
        or not isinstance(data["session_id"], str)
        or re.fullmatch("[0-9a-f]{32}", data["session_id"]) is None
    ):
        raise ViewerAuthorizationError("The Viewer handoff is malformed.")
    validate_context(data["context"])
    role = "ready" if data["consumer"] == "backend" else "desktop"
    if (
        hashlib.sha256(data["ticket"].encode("ascii")).hexdigest() != data["context"]["tickets"][role]
        or (
            data["consumer"] == "desktop" and not data["context"]["development"]
            and data["context"]["desktop"] is None
        )
    ):
        raise ViewerAuthorizationError("The Viewer handoff ticket or desktop payload does not match its consumer.")
    broker = urlsplit(data["broker"])
    try:
        valid = (
            broker.scheme == "http" and broker.hostname is not None and broker.port is not None
            and broker.path == f"/viewer/{data['session_id']}/proof"
            and broker.username is None and broker.password is None and not broker.query and not broker.fragment
        )
    except ValueError as error:
        raise ViewerAuthorizationError("The Viewer broker address is invalid.") from error
    if not valid:
        raise ViewerAuthorizationError("The Viewer broker is not a paired DTS session.")
    return data


class ViewerLease:
    label = "Viewer"

    def __init__(self, handoff: dict, *, issuer_keys: dict[str, str], device_id=None):
        self.handoff = handoff
        self.issuer_keys = issuer_keys
        self.device_id = device_id
        self.deadline = 0.0
        self.wall_deadline = 0.0
        self.last_wall = time.time()
        self.claims = None
        self.renew()

    def current(self) -> None:
        now = time.time()
        if now < self.last_wall - 5:
            raise ViewerAuthorizationError(f"The computer clock moved backwards during {self.label} authorization.")
        self.last_wall = now
        if time.monotonic() >= self.deadline or now >= self.wall_deadline:
            raise ViewerGrantExpired(f"The live DTS {self.label} session expired. Relaunch through DTS.")

    def renew(self) -> None:
        challenge = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        broker = urlsplit(self.handoff["broker"])
        connection = http.client.HTTPConnection(broker.hostname, broker.port, timeout=3)
        started = time.monotonic()
        try:
            connection.request(
                "POST", broker.path,
                canonical({"challenge": challenge, "consumer": self.handoff["consumer"]}),
                {"Content-Type": "application/json", "Authorization": f"Bearer {self.handoff['secret']}"},
            )
            response = connection.getresponse()
            content = response.read(65537)
            if response.status != 200:
                self.deadline = 0.0
                raise ViewerAuthorizationError(f"DTS denied the {self.label} session. Review your authorization and relaunch.")
        except (OSError, http.client.HTTPException) as error:
            raise ViewerBrokerUnavailable(f"The live DTS {self.label} session is unreachable.") from error
        finally:
            connection.close()
        now = time.time()
        if now < self.last_wall - 5:
            self.deadline = 0.0
            raise ViewerAuthorizationError(f"The computer clock moved backwards during {self.label} renewal.")
        claims = self._validate_response(
            decode_json(content, 65536), issuer_keys=self.issuer_keys, challenge=challenge,
            session_id=self.handoff["session_id"], consumer=self.handoff["consumer"],
            context=self.handoff["context"], device_id=self.device_id, now=now,
        )
        self.last_wall = now
        self.wall_deadline = claims["expires_at"]
        self.deadline = min(started + 30, time.monotonic() + claims["expires_at"] - now)
        self.claims = claims
        self.current()

    def _validate_response(self, response, **parameters):
        return validate_proof(response, **parameters)


def relative_path(value: str) -> bool:
    if not isinstance(value, str) or not value or any(c in value for c in ("\\", ":", "\x00")):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and str(path) == value and ".." not in path.parts


def inventory(root: Path, *, windows=False, manifest=MANIFEST) -> dict:
    root = Path(root).resolve()
    result = {}
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if relative == manifest:
                continue
            if not relative_path(relative):
                raise ViewerAuthorizationError("The Viewer release contains an unsafe file name.")
            if path.is_symlink():
                target = os.readlink(path)
                if not path.resolve().is_relative_to(root) or not path.exists():
                    raise ViewerAuthorizationError("The Viewer release contains an escaping or broken symbolic link.")
                result[relative] = {"link": target}
            elif path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                result[relative] = {
                    "sha256": digest.hexdigest(),
                    "executable": relative.endswith(".exe") if windows else bool(path.stat().st_mode & 0o111),
                }
            elif not path.is_dir():
                raise ViewerAuthorizationError("The Viewer release contains a special file.")
    if len({name.casefold() for name in result}) != len(result):
        raise ViewerAuthorizationError("Viewer inventories cannot contain case-ambiguous paths.")
    return result


def verify_release(
    root: Path, *, release_key: str, issuer_keys: dict[str, str], kind="desktop",
    manifest=MANIFEST, audience="duckietown-viewer-release",
) -> dict:
    root = Path(root).resolve()
    try:
        raw = (root / manifest).read_bytes()
        claims, content, signature = envelope(raw)
        verify_signature(release_key, content, signature)
        if (
            set(claims) != {"format", "audience", "kind", "distribution", "version", "platform", "entrypoint", "files", "trust"}
            or type(claims["format"]) is not int or claims["format"] != 1
            or claims["audience"] != audience or claims["kind"] != kind
            or claims["distribution"] != "ente" or not isinstance(claims["version"], str)
            or re.fullmatch(r"\d+\.\d+\.\d+", claims["version"]) is None
            or claims["platform"] not in ("linux", "linux-arm64", "macos", "macos-arm64", "windows", "windows-arm64")
            or not relative_path(claims["entrypoint"])
            or claims["trust"] != {"release": release_key, "issuers": issuer_keys}
            or not isinstance(claims["files"], dict) or not claims["files"]
            or any(not relative_path(name) for name in claims["files"])
            or not (root / claims["entrypoint"]).exists()
            or inventory(root, windows=claims["platform"].startswith("windows"), manifest=manifest) != claims["files"]
        ):
            raise ViewerAuthorizationError("Viewer files do not match their signed release inventory.")
        return {**claims, "sha256": hashlib.sha256(raw).hexdigest(), "root": str(root)}
    except OSError as error:
        raise ViewerAuthorizationError("A signed Viewer release is required. Reinstall using DTS.") from error


def verify_backend_catalog(
    raw: bytes, *, release_key: str, audience="duckietown-viewer-backends",
    repository="dt-duckietown-viewer",
) -> dict:
    claims, content, signature = envelope(raw)
    verify_signature(release_key, content, signature)
    if (
        set(claims) != {"format", "audience", "distribution", "version", "images"}
        or type(claims["format"]) is not int or claims["format"] != 1
        or claims["audience"] != audience or claims["distribution"] != "ente"
        or not isinstance(claims["version"], str) or re.fullmatch(r"\d+\.\d+\.\d+", claims["version"]) is None
        or not isinstance(claims["images"], dict) or not claims["images"]
        or not set(claims["images"]).issubset({"amd64", "arm64v8"})
    ):
        raise ViewerAuthorizationError("The signed Viewer backend catalog is invalid.")
    for image in claims["images"].values():
        if (
            not isinstance(image, dict) or set(image) != {"reference", "config_sha256", "runtime_sha256"}
            or not isinstance(image["reference"], str)
            or re.fullmatch(r"(?:docker\.io/)?duckietown/" + re.escape(repository) + r"@sha256:[0-9a-f]{64}", image["reference"]) is None
            or not is_digest(image["config_sha256"]) or not is_digest(image["runtime_sha256"])
        ):
            raise ViewerAuthorizationError("A Viewer image is not bound to an official immutable digest.")
    return claims


def install_archive(archive_path: Path, destination: Path, *, release_key: str, issuer_keys: dict[str, str], version: str, platform: str) -> dict:
    destination = Path(destination)
    if destination.is_symlink() or destination.name != f"v{version}-{platform}":
        raise ViewerAuthorizationError("The Viewer installation destination is invalid.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".viewer-install-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "payload"
        staging.mkdir()
        try:
            with ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if len(entries) > 100000 or sum(item.file_size for item in entries) > 8 * 1024**3:
                    raise ViewerAuthorizationError("The Viewer archive exceeds safe extraction limits.")
                names = set()
                links = []
                for entry in entries:
                    name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
                    if not relative_path(name) or name.casefold() in names:
                        raise ViewerAuthorizationError("The Viewer archive has duplicate or unsafe paths.")
                    names.add(name.casefold())
                    mode = entry.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        links.append((name, archive.read(entry).decode("utf-8")))
                        continue
                    if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise ViewerAuthorizationError("The Viewer archive contains special files.")
                    archive.extract(entry, staging)
                    if not entry.is_dir():
                        permissions = (mode & 0o755) or 0o644
                        if platform.startswith("windows") and name.endswith(".exe"):
                            permissions |= 0o111
                        (staging / name).chmod(permissions)
                for name, target in links:
                    link = staging / name
                    link.parent.mkdir(parents=True, exist_ok=True)
                    if Path(target).is_absolute() or not (link.parent / target).resolve().is_relative_to(staging):
                        raise ViewerAuthorizationError("The Viewer archive contains an escaping symbolic link.")
                    link.symlink_to(target)
        except (OSError, BadZipFile, UnicodeError) as error:
            raise ViewerAuthorizationError(f"Could not safely unpack the Viewer release: {error}") from error
        claims = verify_release(staging, release_key=release_key, issuer_keys=issuer_keys)
        if claims["version"] != version or claims["platform"] != platform:
            raise ViewerAuthorizationError("The signed Viewer release is for a different version or platform.")
        backup = Path(temporary) / "previous"
        if destination.exists():
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise
    return {**claims, "root": str(destination.resolve())}


def authorize_backend(module: str, root: Path) -> ViewerLease:
    path = os.environ.get("DT_VIEWER_HANDOFF")
    if not path:
        raise ViewerAuthorizationError(
            "The Duckietown Viewer requires a live authorized DTS session. "
            "Use a 'dts duckiebot' Viewer command; source work requires Viewer developer authorization."
        )
    handoff = read_handoff(Path(path))
    if handoff["consumer"] != "backend" or module != handoff["context"]["app"]:
        raise ViewerAuthorizationError("The backend module does not match its authorized Viewer app.")
    release_key, issuer_keys = native_trust()
    if not handoff["context"]["development"]:
        release = verify_release(root, release_key=release_key, issuer_keys=issuer_keys, kind="backend")
        if release["sha256"] != handoff["context"]["backend"]:
            raise ViewerAuthorizationError("The backend payload does not match this Viewer launch.")
    return ViewerLease(handoff, issuer_keys=issuer_keys)


def _desktop_lease(handoff_path: Path, url: str, *, development: bool) -> ViewerLease:
    handoff = read_handoff(handoff_path)
    if handoff["consumer"] != "desktop" or url != handoff["context"]["endpoint"]:
        raise ViewerAuthorizationError("The desktop URL does not match its paired Viewer session.")
    if development != handoff["context"]["development"]:
        raise ViewerAuthorizationError("Source desktop launches require Viewer developer authorization.")
    release_key, issuer_keys = native_trust()
    if not development:
        executable = Path(sys.executable).resolve()
        root = next((parent for parent in executable.parents if (parent / MANIFEST).is_file()), None)
        if root is None:
            raise ViewerAuthorizationError("The packaged desktop guard has no signed release inventory.")
        release = verify_release(root, release_key=release_key, issuer_keys=issuer_keys)
        if release["sha256"] != handoff["context"]["desktop"]:
            raise ViewerAuthorizationError("The desktop payload does not match this launch.")
    import duckietown_viewer_guard_device as device
    try:
        device_id = device.get_device_id()
    except device.DeviceIdentityError as error:
        raise ViewerAuthorizationError(str(error)) from error
    return ViewerLease(handoff, issuer_keys=issuer_keys, device_id=device_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Native Duckietown Viewer session guard")
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        lease = _desktop_lease(args.handoff, args.url, development=args.development)
        print(canonical({"authorized": True, "ticket": lease.handoff["ticket"]}).decode("ascii"), flush=True)
        while True:
            time.sleep(1)
            lease.current()
            if lease.deadline - time.monotonic() <= 20:
                try:
                    lease.renew()
                except ViewerBrokerUnavailable as error:
                    print(str(error), file=sys.stderr, flush=True)
                    lease.current()
    except (ViewerAuthorizationError, OSError, ImportError) as error:
        print(f"Viewer authorization failed: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from error
