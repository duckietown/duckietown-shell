"""Signed renderer releases and live, Hub-authorized DTS launch sessions."""

import base64
import binascii
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import tempfile
import threading
import time
from typing import Optional
from zipfile import BadZipFile, ZipFile

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from filelock import FileLock, Timeout

import dt_shell_device
from . import logger
from .authorization import _identity, _result, _validate_plan_grace
from .constants import DTHUB_URL
from .exceptions import UserError


RENDERER_MANIFEST = "duckiematrix.release.json"
GRANT_AUDIENCE = "duckiematrix-renderer"
PROOF_AUDIENCE = "duckiematrix-renderer-session"
USE_CAPABILITY = "use:duckiematrix-renderer"
DEVELOP_CAPABILITY = "develop:duckiematrix-renderer"
LEASE_SECONDS = 30
MAX_JSON_BYTES = 1024 * 1024
GRANT_FIELDS = {
    "format",
    "audience",
    "capability",
    "issuer",
    "uid",
    "identity_sha256",
    "device_id",
    "launch_key",
    "is_staff",
    "is_superuser",
    "base_plan",
    "entitlement_expiration",
    "issued_at",
    "expires_at",
    "renewable",
}


class RendererHubUnavailable(UserError):
    pass


class RendererGrantExpired(UserError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UserError("Renderer authorization contains a duplicate JSON field.")
        result[key] = value
    return result


def _json(content: bytes, limit: int = MAX_JSON_BYTES):
    if len(content) > limit:
        raise UserError("Renderer authorization data exceeds its size limit.")
    try:
        return json.loads(content, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError) as error:
        raise UserError("Renderer authorization data is not valid JSON.") from error


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _hex(value, length=64) -> bool:
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def _signed(content: bytes, key: Ed25519PrivateKey) -> dict:
    return {
        "payload": base64.b64encode(content).decode("ascii"),
        "signature": base64.b64encode(key.sign(content)).decode("ascii"),
    }


def _envelope(value: bytes) -> tuple[dict, bytes, bytes]:
    envelope = _json(value)
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"payload", "signature"}
        or not all(isinstance(item, str) for item in envelope.values())
    ):
        raise UserError("Renderer authorization has an invalid signed envelope.")
    try:
        content = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
    except (ValueError, binascii.Error) as error:
        raise UserError("Renderer authorization has invalid base64 data.") from error
    claims = _json(content)
    try:
        canonical = _canonical(claims)
    except (ValueError, TypeError) as error:
        raise UserError("Renderer authorization contains invalid JSON values.") from error
    if not isinstance(claims, dict) or canonical != content or len(signature) != 64:
        raise UserError("Renderer authorization has a noncanonical signed payload.")
    return claims, content, signature


def _verify_signature(key: str, content: bytes, signature: bytes) -> None:
    if not _hex(key):
        raise UserError("Renderer verification has an invalid trusted public key.")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(signature, content)
    except InvalidSignature as error:
        raise UserError("Renderer authorization signature verification failed.") from error


def _trust() -> tuple[str, dict[str, str]]:
    try:
        from dt_shell_release import ReleaseIntegrityError, renderer_trust
    except ImportError as error:
        raise UserError(
            "Renderer authorization requires an official native DTS installation. "
            "Use DTS 6.3.0 or newer; source overrides require authenticated developer mode."
        ) from error
    try:
        return renderer_trust()
    except ReleaseIntegrityError as error:
        raise UserError(f"The native DTS renderer session is no longer authorized: {error}") from error


def _relative(value: str) -> bool:
    if not isinstance(value, str) or "\\" in value or ":" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and str(path) == value and ".." not in path.parts


def _inventory(root: Path) -> dict[str, str]:
    files = {}
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            if path.is_dir() or not path.resolve().is_relative_to(root):
                raise UserError("Renderer releases cannot contain directory or escaping symbolic links.")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name in (RENDERER_MANIFEST, ".release.json"):
                continue
            if not _relative(name):
                raise UserError("A renderer release contains an unsafe file path.")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[name] = digest.hexdigest()
    return files


def verify_renderer_release(
    directory: Path, *, version: Optional[str] = None, os_family: Optional[str] = None
) -> dict:
    root = Path(directory).resolve()
    try:
        claims, content, signature = _envelope((root / RENDERER_MANIFEST).read_bytes())
        key, _ = _trust()
        _verify_signature(key, content, signature)
        if (
            set(claims)
            != {
                "format",
                "audience",
                "version",
                "os_family",
                "backend",
                "entrypoint",
                "files",
                "trust",
            }
            or type(claims["format"]) is not int
            or claims["format"] != 1
            or claims["audience"] != "duckiematrix-release"
            or not isinstance(claims["version"], str)
            or re.fullmatch(r"\d+\.\d+\.\d+", claims["version"]) is None
            or claims["os_family"] not in ("linux", "macos", "windows", "webgl")
            or claims["backend"] != "IL2CPP"
            or not _relative(claims["entrypoint"])
            or not isinstance(claims["files"], dict)
            or not claims["files"]
            or any(not _relative(name) or not _hex(digest) for name, digest in claims["files"].items())
            or (version is not None and claims["version"] != version)
            or (os_family is not None and claims["os_family"] != os_family)
        ):
            raise UserError("The signed renderer inventory does not match the requested release.")
        _, issuer_keys = _trust()
        if claims["trust"] != {"release": key, "issuers": issuer_keys}:
            raise UserError("The renderer release and this DTS installation use different trust identities.")
        expected_entry = {
            "linux": "duckiematrix.x86_64",
            "macos": "duckiematrix.app",
            "windows": "Duckiematrix.exe",
            "webgl": "duckiematrix/index.html",
        }[claims["os_family"]]
        if claims["entrypoint"] != expected_entry or not (root / expected_entry).exists():
            raise UserError("The signed renderer entrypoint is missing or invalid.")
        if _inventory(root) != claims["files"]:
            raise UserError("Renderer files do not match their signed inventory. Reinstall the renderer.")
        return {
            **claims,
            "sha256": hashlib.sha256(content).hexdigest(),
            "root": str(root),
        }
    except OSError as error:
        raise UserError(f"Could not verify the renderer release: {error}") from error


def install_renderer_archive(archive_path: Path, destination: Path, *, version: str, os_family: str) -> None:
    destination = Path(destination)
    if (
        re.fullmatch(r"\d+\.\d+\.\d+", version) is None
        or os_family not in ("linux", "macos", "windows", "webgl")
        or destination.name != f"v{version}-{os_family}"
        or destination.is_symlink()
    ):
        raise UserError("The renderer installation destination or version is invalid.")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".renderer-install-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "release"
        staging.mkdir()
        try:
            with ZipFile(archive_path) as archive:
                if (
                    len(archive.infolist()) > 100000
                    or sum(entry.file_size for entry in archive.infolist()) > 10 * 1024**3
                ):
                    raise UserError("The renderer archive exceeds its safe extraction limits.")
                names = set()
                for entry in archive.infolist():
                    name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
                    if not _relative(name) or name.casefold() in names:
                        raise UserError("The renderer archive has an unsafe or duplicate path.")
                    names.add(name.casefold())
                    mode = entry.external_attr >> 16
                    if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise UserError("The renderer archive contains an unsupported file type.")
                    archive.extract(entry, staging)
                    if not entry.is_dir():
                        (staging / entry.filename).chmod((mode & 0o755) or 0o644)
        except (OSError, BadZipFile) as error:
            raise UserError(f"Could not unpack the renderer archive: {error}") from error
        verify_renderer_release(staging, version=version, os_family=os_family)
        backup = Path(temporary) / "previous"
        if destination.exists():
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise


def validate_renderer_grant(
    token: str,
    *,
    issuer_keys: dict[str, str],
    issuer: str,
    uid: int,
    identity_sha256: str,
    device_id: str,
    launch_key: str,
    development: bool,
    now: Optional[float] = None,
) -> dict:
    if not isinstance(token, str):
        raise UserError("The Hub did not provide a renderer authorization.")
    claims, content, signature = _envelope(token.encode("utf-8"))
    if issuer not in issuer_keys or claims.get("issuer") != issuer:
        raise UserError("The renderer authorization has an unapproved issuer.")
    _verify_signature(issuer_keys[issuer], content, signature)
    capability = DEVELOP_CAPABILITY if development else USE_CAPABILITY
    limit = 3600 if development else 86400
    now = time.time() if now is None else now
    if (
        set(claims) not in (GRANT_FIELDS, GRANT_FIELDS | {"plan_grace_until"})
        or type(claims["format"]) is not int
        or claims["format"] != 1
        or claims["audience"] != GRANT_AUDIENCE
        or claims["capability"] != capability
        or type(claims["uid"]) is not int
        or claims["uid"] <= 0
        or claims["uid"] != uid
        or claims["identity_sha256"] != identity_sha256
        or claims["device_id"] != device_id
        or not _hex(claims["device_id"])
        or claims["launch_key"] != launch_key
        or not _hex(claims["launch_key"])
        or type(claims["is_staff"]) is not bool
        or type(claims["is_superuser"]) is not bool
        or (claims["base_plan"] is not None and not isinstance(claims["base_plan"], str))
        or claims["renewable"] is not False
        or type(claims["issued_at"]) is not int
        or type(claims["expires_at"]) is not int
        or claims["issued_at"] > now + 60
        or claims["issued_at"] <= 0
        or not 0 < claims["expires_at"] - claims["issued_at"] <= limit
    ):
        raise UserError(
            "The renderer authorization does not match this account, computer, launch key or permission."
        )
    grace_until = _validate_plan_grace(claims, claims["expires_at"])
    privileged = claims["is_staff"] or claims["is_superuser"]
    if (development and not privileged) or (
        not privileged
        and grace_until is None
        and claims["base_plan"] not in ("independent_user", "institutional_user")
    ):
        raise UserError(
            "The renderer authorization does not grant the required plan or developer permission."
        )
    end = claims["entitlement_expiration"]
    if end is not None and (
        type(end) not in (int, float) or not math.isfinite(end) or end < claims["expires_at"]
    ):
        raise UserError("The renderer authorization extends beyond its qualifying plan.")
    if claims["expires_at"] <= now:
        raise RendererGrantExpired("The renderer authorization has expired.")
    return claims


def _private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".renderer-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _cache_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise UserError("The renderer cache must contain regular files, not symbolic links.")
    with path.open("rb") as stream:
        content = stream.read(65537)
    if len(content) > 65536:
        raise UserError("A renderer cache file exceeds its size limit.")
    return content


class RendererSession:
    def __init__(
        self,
        shell,
        *,
        os_family: str,
        release: Optional[dict] = None,
        development: bool = False,
        renew: bool = False,
    ):
        self.shell = shell
        self.development = development
        self.release = release
        if not development and release is None:
            raise UserError("Normal renderer sessions require a verified official release.")
        if shell.profile is None or shell.profile.distro is None or shell.profile.distro.name != "ente":
            raise UserError("Duckiematrix is exclusive to 'ente'. Select an 'ente' DTS profile.")
        _, self.issuer_keys = _trust()
        self.issuer = DTHUB_URL.rstrip("/")
        if self.issuer not in self.issuer_keys:
            raise UserError("This Hub URL is not an approved renderer-authorization issuer.")
        self.identity, identity = _identity(shell)
        self.uid = identity.uid
        self.identity_sha256 = hashlib.sha256(self.identity.encode("utf-8")).hexdigest()
        try:
            self.parameters = dt_shell_device.get_device_parameters()
            self.renderer_device_id = dt_shell_device.get_renderer_device_id(os_family)
        except dt_shell_device.DeviceIdentityError as error:
            raise UserError(str(error)) from error
        cache_id = hashlib.sha256(
            f"{self.issuer}:{self.identity_sha256}:{self.parameters['device_id']}".encode("ascii")
        ).hexdigest()
        cache = Path(shell.profile.database("renderer").yaml).parent / "renderer-sessions"
        self.key_path = cache / f"{cache_id}.pem"
        self.grant_path = cache / f"{cache_id}-{'develop' if development else 'use'}.json"
        try:
            cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            with FileLock(str(self.key_path) + ".lock", timeout=60):
                if self.key_path.exists() or self.key_path.is_symlink():
                    key = serialization.load_pem_private_key(_cache_bytes(self.key_path), password=None)
                    if not isinstance(key, Ed25519PrivateKey):
                        raise UserError("The renderer launch-key cache is not an Ed25519 key.")
                    self.key = key
                else:
                    self.key = Ed25519PrivateKey.generate()
                    _private_write(
                        self.key_path,
                        self.key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        ),
                    )
            self.launch_key = (
                self.key.public_key()
                .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
                .hex()
            )
            if (self.grant_path.exists() or self.grant_path.is_symlink()) and not renew:
                self.grant = _cache_bytes(self.grant_path).decode("ascii")
                try:
                    self.claims = self._validate(self.grant)
                except RendererGrantExpired:
                    self._refresh()
                else:
                    if self.claims["expires_at"] - time.time() <= 300:
                        try:
                            self._refresh()
                        except RendererHubUnavailable as error:
                            logger.warning(str(error))
            else:
                self._refresh()
        except (OSError, ValueError, UnicodeError, Timeout) as error:
            raise UserError(
                f"Could not read or save the renderer authorization cache: {error}. "
                "Repair the cache; invalid cache data is not accepted."
            ) from error
        self.deadline = time.monotonic() + (self.claims["expires_at"] - time.time())
        self.last_wall = time.time()
        self.session_id = secrets.token_hex(16)
        self.error: Optional[str] = None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.origin: Optional[str] = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                logger.debug("Renderer session: " + (format % args))

            def _reply(self, status, body):
                content = _canonical(body)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Vary", "Origin")
                if owner.origin is not None and self.headers.get("Origin") == owner.origin:
                    self.send_header("Access-Control-Allow-Origin", owner.origin)
                self.end_headers()
                self.wfile.write(content)

            def _allowed(self):
                return self.path == owner.path and (
                    self.headers.get("Origin") is None or self.headers.get("Origin") == owner.origin
                )

            def do_OPTIONS(self):
                if not self._allowed():
                    self._reply(403, {"error": "Renderer session origin or path was rejected."})
                    return
                self.send_response(204)
                if owner.origin is not None:
                    self.send_header("Access-Control-Allow-Origin", owner.origin)
                self.send_header("Access-Control-Allow-Methods", "POST")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Max-Age", "30")
                self.end_headers()

            def do_POST(self):
                if not self._allowed():
                    self._reply(403, {"error": "Renderer session origin or path was rejected."})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 4096:
                        raise UserError("The renderer challenge has an invalid size.")
                    self.connection.settimeout(3)
                    request = _json(self.rfile.read(length), 4096)
                    if not isinstance(request, dict) or set(request) != {"challenge"}:
                        raise UserError("The renderer challenge has an invalid structure.")
                    response = owner.proof(request["challenge"])
                except (UserError, ValueError, OSError) as error:
                    logger.error(f"Renderer session request denied: {error}")
                    self._reply(403, {"error": str(error)})
                    return
                self._reply(200, response)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.path = f"/renderer/{self.session_id}/proof"
        self.url = f"http://127.0.0.1:{self.server.server_port}{self.path}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.maintenance = threading.Thread(target=self._maintain, daemon=True)
        self.thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            try:
                connection.request(
                    "POST",
                    self.path,
                    body=_canonical({"challenge": base64.b64encode(secrets.token_bytes(32)).decode("ascii")}),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                if response.status != 200 or "proof" not in _json(response.read(MAX_JSON_BYTES + 1)):
                    raise UserError("The renderer session broker did not become responsive.")
            finally:
                connection.close()
        except (OSError, http.client.HTTPException, UserError):
            self.close()
            raise
        self.maintenance.start()

    def _validate(self, grant: str) -> dict:
        return validate_renderer_grant(
            grant,
            issuer_keys=self.issuer_keys,
            issuer=self.issuer,
            uid=self.uid,
            identity_sha256=self.identity_sha256,
            device_id=self.parameters["device_id"],
            launch_key=self.launch_key,
            development=self.development,
        )

    def _request(self) -> str:
        try:
            with requests.post(
                self.issuer + "/api/v1/auth/token/renderer/",
                headers={"Authorization": f"Token {self.identity}"},
                json={
                    **self.parameters,
                    "launch_key": self.launch_key,
                    "development": self.development,
                },
                timeout=(5, 10),
                allow_redirects=False,
                stream=True,
            ) as response:
                if 300 <= response.status_code < 400:
                    raise UserError("The renderer authorization endpoint redirected the request.")
                if 400 <= response.status_code < 500:
                    raise UserError(
                        f"Duckietown Hub rejected renderer authorization (HTTP {response.status_code})."
                    )
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if len(content) + len(chunk) > 65536:
                        raise UserError("The Hub renderer authorization response exceeds its size limit.")
                    content.extend(chunk)
        except requests.RequestException as error:
            raise RendererHubUnavailable(
                "Could not contact Duckietown Hub for renderer authorization. "
                "Offline use requires an unexpired cached renderer permission."
            ) from error
        payload = _json(bytes(content), 65536)
        if not isinstance(payload, dict):
            raise UserError("The Hub returned an invalid renderer authorization response.")
        result = _result(payload)
        token = result.get("token")
        if not isinstance(token, str):
            raise UserError("The Hub did not return a signed renderer permission.")
        return token

    def _refresh(self) -> None:
        grant = self._request()
        claims = self._validate(grant)
        _private_write(self.grant_path, grant.encode("ascii"))
        self.grant, self.claims = grant, claims

    def _current(self) -> None:
        _trust()
        identity, token = _identity(self.shell)
        if identity != self.identity or token.uid != self.uid:
            raise UserError("The active DTS identity changed during the renderer session.")
        try:
            device_id = dt_shell_device.get_device_id()
        except dt_shell_device.DeviceIdentityError as error:
            raise UserError(str(error)) from error
        if device_id != self.parameters["device_id"]:
            raise UserError("The DTS computer identity changed during the renderer session.")

    def proof(self, challenge: str) -> dict:
        try:
            decoded = base64.b64decode(challenge, validate=True)
        except (ValueError, TypeError, binascii.Error) as error:
            raise UserError("The renderer challenge is not valid base64.") from error
        if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != challenge:
            raise UserError("The renderer challenge must contain 32 random bytes.")
        self._current()
        with self.lock:
            if self.stop_event.is_set() or self.error is not None:
                raise UserError(self.error or "The DTS renderer session is closed.")
            now = time.time()
            if now < self.last_wall - 5:
                self.error = "The computer clock moved backwards during renderer authorization."
                raise UserError(self.error)
            self.last_wall = now
            if now >= self.claims["expires_at"] or time.monotonic() >= self.deadline:
                raise RendererGrantExpired("The DTS renderer permission has expired.")
            claims = {
                "format": 1,
                "audience": PROOF_AUDIENCE,
                "session_id": self.session_id,
                "challenge": challenge,
                "grant_sha256": hashlib.sha256(self.grant.encode("ascii")).hexdigest(),
                "uid": self.uid,
                "identity_sha256": self.identity_sha256,
                "device_id": self.parameters["device_id"],
                "renderer_device_id": self.renderer_device_id,
                "artifact_sha256": None if self.release is None else self.release["sha256"],
                "issued_at": int(now),
                "expires_at": min(int(now) + LEASE_SECONDS, self.claims["expires_at"]),
            }
            return {"grant": self.grant, "proof": _signed(_canonical(claims), self.key)}

    def _maintain(self) -> None:
        while not self.stop_event.wait(min(30, max(1, (self.claims["expires_at"] - time.time()) / 2))):
            try:
                self._current()
                if self.claims["expires_at"] - time.time() > 300:
                    continue
                grant = self._request()
                claims = self._validate(grant)
                _private_write(self.grant_path, grant.encode("ascii"))
                with self.lock:
                    self.grant, self.claims = grant, claims
                    self.deadline = time.monotonic() + (claims["expires_at"] - time.time())
            except RendererHubUnavailable as error:
                logger.warning(str(error))
                if time.monotonic() < self.deadline:
                    continue
                with self.lock:
                    self.error = "The renderer permission expired while Duckietown Hub was unavailable."
            except (UserError, OSError) as error:
                logger.error(f"Renderer session authorization ended: {error}")
                with self.lock:
                    self.error = str(error)
            if self.error is not None:
                return

    def close(self) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.maintenance.is_alive() and threading.current_thread() is not self.maintenance:
            self.maintenance.join(timeout=20)
