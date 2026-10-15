import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import datetime
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile, ZipInfo

import requests
from urllib3.exceptions import ReadTimeoutError

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dt_shell.exceptions import UserError
from dt_shell.authorization import ENTE_PLAN_ENFORCEMENT_START
from dt_shell import renderer
import dt_shell_device


ISSUERS = ("https://hub.duckietown.com", "https://staging-hub.duckietown.com")
IDENTITY = "test-identity-not-a-renderer-credential"
UID = 42
DEVICE = "a" * 64


def public(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


class RendererFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.keys = {issuer: Ed25519PrivateKey.generate() for issuer in ISSUERS}
        self.issuers = {issuer: public(key) for issuer, key in self.keys.items()}
        self.release_key = Ed25519PrivateKey.generate()
        self.release_public = public(self.release_key)
        self.identity_sha256 = hashlib.sha256(IDENTITY.encode()).hexdigest()

    def grant(self, key, *, development=False, changes=None, issuer=ISSUERS[0], now=None):
        now = int(time.time()) if now is None else now
        claims = {
            "format": 1,
            "audience": renderer.GRANT_AUDIENCE,
            "capability": renderer.DEVELOP_CAPABILITY if development else renderer.USE_CAPABILITY,
            "issuer": issuer,
            "uid": UID,
            "identity_sha256": self.identity_sha256,
            "device_id": DEVICE,
            "launch_key": key,
            "is_staff": development,
            "is_superuser": False,
            "base_plan": None if development else "independent_user",
            "entitlement_expiration": None,
            "issued_at": now,
            "expires_at": now + (3600 if development else 86400),
            "renewable": False,
        }
        claims.update(changes or {})
        return renderer._canonical(renderer._signed(renderer._canonical(claims), self.keys[issuer])).decode(
            "ascii"
        )

    def release(self, platform="linux", name=None):
        root = self.root / (name or platform)
        root.mkdir(parents=True)
        entry = {
            "linux": "duckiematrix.x86_64",
            "windows": "Duckiematrix.exe",
            "macos": "duckiematrix.app/Contents/MacOS/duckiematrix",
            "webgl": "duckiematrix/index.html",
        }[platform]
        path = root / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            b"compiled-fixture-only\n"
            + self.release_public.encode("ascii")
            + json.dumps(self.issuers, sort_keys=True, separators=(",", ":")).encode("ascii")
            + b"duckiematrix-renderer-official-v1"
        )
        path.chmod(0o755)
        metadata = {
            "version": "0.12.0",
            "scripting_backend": "IL2CPP",
            "target": {"operating_system_family": platform},
            "authorization": {
                "protocol": 1,
                "official_release": True,
                "release_key": self.release_public,
                "issuer_keys": json.dumps(self.issuers, sort_keys=True, separators=(",", ":")),
            },
        }
        (root / "Duckiematrix.json").write_text(json.dumps(metadata), encoding="ascii")
        claims = {
            "format": 1,
            "audience": "duckiematrix-release",
            "version": "0.12.0",
            "os_family": platform,
            "backend": "IL2CPP",
            "entrypoint": "duckiematrix.app" if platform == "macos" else entry,
            "files": renderer._inventory(root),
            "trust": {"release": self.release_public, "issuers": self.issuers},
        }
        (root / renderer.RENDERER_MANIFEST).write_bytes(
            renderer._canonical(renderer._signed(renderer._canonical(claims), self.release_key))
        )
        return root

    def signed_proof(self, grant, launch_key, *, changes=None, now=None):
        now = int(time.time()) if now is None else now
        claims = {
            "format": 1,
            "audience": renderer.PROOF_AUDIENCE,
            "session_id": "d" * 32,
            "challenge": base64.b64encode(b"n" * 32).decode("ascii"),
            "grant_sha256": hashlib.sha256(grant.encode("ascii")).hexdigest(),
            "uid": UID,
            "identity_sha256": self.identity_sha256,
            "device_id": DEVICE,
            "renderer_device_id": DEVICE,
            "artifact_sha256": "e" * 64,
            "issued_at": now,
            "expires_at": now + 30,
        }
        claims.update(changes or {})
        return renderer._canonical(
            {
                "grant": grant,
                "proof": renderer._signed(renderer._canonical(claims), launch_key),
            }
        ).decode("ascii")


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dts-renderer-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = RendererFixture(self.root)
        self.launch_key = Ed25519PrivateKey.generate()
        self.launch_public = public(self.launch_key)
        self.shell = SimpleNamespace(
            profile=SimpleNamespace(
                distro=SimpleNamespace(name="ente"),
                database=lambda name: SimpleNamespace(yaml=str(self.root / f"{name}.yaml")),
            )
        )
        for mock in (
            patch(
                "dt_shell.renderer._trust",
                return_value=(self.fixture.release_public, self.fixture.issuers),
            ),
            patch(
                "dt_shell.renderer._identity",
                return_value=(IDENTITY, SimpleNamespace(uid=UID)),
            ),
            patch("dt_shell.renderer.DTHUB_URL", ISSUERS[0]),
            patch(
                "dt_shell_device.get_device_parameters",
                return_value={"device_id": DEVICE, "device_hostname": "computer"},
            ),
            patch("dt_shell_device.get_device_id", return_value=DEVICE),
            patch("dt_shell_device.get_renderer_device_id", return_value=DEVICE),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def validate(self, token, *, development=False, **kwargs):
        return renderer.validate_renderer_grant(
            token,
            issuer_keys=self.fixture.issuers,
            issuer=ISSUERS[0],
            uid=UID,
            identity_sha256=self.fixture.identity_sha256,
            device_id=DEVICE,
            launch_key=self.launch_public,
            development=development,
            **kwargs,
        )

    def session(self, *, development=False, renew=False):
        fixture = self.fixture

        def request(session):
            return fixture.grant(session.launch_key, development=session.development)

        with patch.object(renderer.RendererSession, "_request", new=request):
            session = renderer.RendererSession(
                self.shell,
                os_family="linux",
                development=development,
                renew=renew,
                release=None if development else {"sha256": "e" * 64},
            )
        self.addCleanup(session.close)
        return session

    def test_production_and_staging_signatures_are_pinned_separately(self):
        self.validate(self.fixture.grant(self.launch_public))
        staging = self.fixture.grant(self.launch_public, issuer=ISSUERS[1])
        renderer.validate_renderer_grant(
            staging,
            issuer_keys=self.fixture.issuers,
            issuer=ISSUERS[1],
            uid=UID,
            identity_sha256=self.fixture.identity_sha256,
            device_id=DEVICE,
            launch_key=self.launch_public,
            development=False,
        )
        with self.assertRaisesRegex(UserError, "issuer"):
            self.validate(staging)
        swapped = dict(zip(ISSUERS, reversed(list(self.fixture.issuers.values()))))
        with patch.dict(self.fixture.issuers, swapped), self.assertRaisesRegex(UserError, "signature"):
            self.validate(self.fixture.grant(self.launch_public))

    def test_missing_tampered_duplicate_noncanonical_and_wrong_signatures_are_denied(
        self,
    ):
        original = self.fixture.grant(self.launch_public)
        envelope = json.loads(original)
        for token in (
            None,
            "",
            "{}",
            '{"payload":"bad","signature":"bad"}',
            original.replace('"payload":', '"payload":"bad","payload":', 1),
            renderer._canonical({**envelope, "signature": base64.b64encode(b"x" * 64).decode()}).decode(),
        ):
            with self.subTest(token=token is None), self.assertRaises(UserError):
                self.validate(token)
        claims = json.loads(base64.b64decode(envelope["payload"]))
        indented = json.dumps(claims, indent=2).encode()
        with self.assertRaisesRegex(UserError, "noncanonical"):
            self.validate(
                renderer._canonical(renderer._signed(indented, self.fixture.keys[ISSUERS[0]])).decode()
            )

    def test_account_identity_device_launch_key_scope_and_types_are_bound(self):
        for changes in (
            {"uid": UID + 1},
            {"uid": True},
            {"format": True},
            {"renewable": True},
            {"identity_sha256": "b" * 64},
            {"device_id": "b" * 64},
            {"launch_key": "b" * 64},
            {"audience": "duckietown-shell-developer"},
            {"capability": "use:ente"},
            {"is_staff": 1},
            {"is_superuser": "false"},
            {"extra": True},
            {"base_plan": "instructor"},
            {"issued_at": int(time.time()) + 120},
            {"expires_at": int(time.time()) + 86401},
            {"entitlement_expiration": int(time.time()) + 60},
        ):
            with self.subTest(changes=changes), self.assertRaises(UserError):
                self.validate(self.fixture.grant(self.launch_public, changes=changes))

    def test_privileged_grants_still_expire_and_do_not_cross_permissions(self):
        for development in (False, True):
            token = self.fixture.grant(
                self.launch_public,
                development=development,
                changes={"is_staff": False, "is_superuser": True, "base_plan": None},
                now=int(time.time()) - 86401,
            )
            with self.assertRaises(renderer.RendererGrantExpired):
                self.validate(token, development=development)
        developer = self.fixture.grant(self.launch_public, development=True)
        self.validate(developer, development=True)
        with self.assertRaises(UserError):
            self.validate(developer)
        with self.assertRaises(UserError):
            self.validate(self.fixture.grant(self.launch_public), development=True)

    def test_signed_plan_grace_is_valid_before_but_not_at_or_after_the_cutoff(self):
        deadline = int(datetime.datetime(2027, 2, 1, tzinfo=datetime.timezone.utc).timestamp())
        token = self.fixture.grant(
            self.launch_public,
            now=deadline - 1,
            changes={"base_plan": None, "plan_grace_until": deadline, "expires_at": deadline},
        )
        claims = self.validate(token, now=deadline - 1)
        self.assertEqual(deadline, claims["expires_at"])
        for now in (deadline, deadline + 1):
            with self.subTest(now=now), self.assertRaises(renderer.RendererGrantExpired):
                self.validate(token, now=now)

    def test_plan_grace_cannot_extend_access_or_waive_other_bindings(self):
        deadline = int(ENTE_PLAN_ENFORCEMENT_START.timestamp())
        grace = {"base_plan": None, "plan_grace_until": deadline, "expires_at": deadline}
        for changes in (
            {"plan_grace_until": None},
            {"plan_grace_until": str(deadline)},
            {"plan_grace_until": True},
            {"plan_grace_until": float(deadline)},
            {"plan_grace_until": deadline + 1},
            {"expires_at": deadline + 1},
            {"base_plan": "independent_user"},
            {"is_staff": True},
            {"is_superuser": True},
            {"entitlement_expiration": deadline},
            {"device_id": "b" * 64},
            {"launch_key": "b" * 64},
            {"capability": renderer.DEVELOP_CAPABILITY},
        ):
            token = self.fixture.grant(self.launch_public, now=deadline - 1, changes={**grace, **changes})
            with self.subTest(changes=changes), self.assertRaises(UserError):
                self.validate(token, now=deadline - 1)
        token = self.fixture.grant(self.launch_public, now=deadline - 1, changes=grace)
        with self.assertRaises(UserError):
            self.validate(token, development=True, now=deadline - 1)

    def test_live_grace_proofs_stop_at_cutoff_and_offline_cache_cannot_restart(self):
        deadline = int(ENTE_PLAN_ENFORCEMENT_START.timestamp())

        def request(session):
            return self.fixture.grant(
                session.launch_key,
                now=deadline - 10,
                changes={"base_plan": None, "plan_grace_until": deadline, "expires_at": deadline},
            )

        with patch("dt_shell.renderer.time.time", return_value=deadline - 10) as wall, patch.object(
            renderer.RendererSession, "_request", new=request
        ):
            session = renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
            self.addCleanup(session.close)
            challenge = base64.b64encode(b"c" * 32).decode("ascii")
            proof = session.proof(challenge)
            claims = json.loads(base64.b64decode(proof["proof"]["payload"]))
            self.assertEqual(deadline, claims["expires_at"])
            wall.return_value = deadline
            with self.assertRaises(renderer.RendererGrantExpired):
                session.proof(challenge)
            session.close()
            with patch.object(
                renderer.RendererSession,
                "_request",
                side_effect=renderer.RendererHubUnavailable("offline"),
            ) as request, self.assertRaisesRegex(renderer.RendererHubUnavailable, "offline"):
                renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
            request.assert_called_once()

    def test_all_four_release_layouts_are_verified_and_mutable_checksums_are_not_authority(
        self,
    ):
        for platform in ("linux", "macos", "windows", "webgl"):
            with self.subTest(platform=platform):
                root = self.fixture.release(platform)
                (root / ".release.json").write_text('{"checksum":"untrusted"}')
                result = renderer.verify_renderer_release(root, version="0.12.0", os_family=platform)
                self.assertEqual(platform, result["os_family"])
                self.assertEqual(64, len(result["sha256"]))

    def test_altered_removed_added_and_wrong_version_renderer_files_are_denied(self):
        for change in ("alter", "remove", "add", "version"):
            root = self.fixture.release(name=change)
            executable = root / "duckiematrix.x86_64"
            if change == "alter":
                executable.write_bytes(b"tampered")
            elif change == "remove":
                executable.unlink()
            elif change == "add":
                (root / "injected.dll").write_bytes(b"extra")
            with self.subTest(change=change), self.assertRaises(UserError):
                renderer.verify_renderer_release(root, version="0.13.0" if change == "version" else "0.12.0")

    def test_escaping_and_directory_symlinks_are_denied(self):
        root = self.fixture.release()
        (root / "outside.dll").symlink_to(self.root / "outside-secret")
        (self.root / "outside-secret").write_bytes(b"outside")
        with self.assertRaisesRegex(UserError, "symbolic"):
            renderer.verify_renderer_release(root)
        (root / "outside.dll").unlink()
        (root / "linked").symlink_to(root, target_is_directory=True)
        with self.assertRaisesRegex(UserError, "symbolic"):
            renderer.verify_renderer_release(root)

    def archive(self, root, destination):
        with ZipFile(destination, "w") as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())

    def test_signed_archive_install_is_atomic_and_preserves_executable_mode(self):
        root = self.fixture.release()
        archive = self.root / "renderer.zip"
        self.archive(root, archive)
        destination = self.root / "installed/v0.12.0-linux"
        renderer.install_renderer_archive(archive, destination, version="0.12.0", os_family="linux")
        renderer.verify_renderer_release(destination)
        self.assertTrue((destination / "duckiematrix.x86_64").stat().st_mode & stat.S_IXUSR)
        (root / "duckiematrix.x86_64").write_bytes(b"invalid update")
        self.archive(root, archive)
        with self.assertRaises(UserError):
            renderer.install_renderer_archive(archive, destination, version="0.12.0", os_family="linux")
        renderer.verify_renderer_release(destination)

    def test_archive_path_traversal_duplicate_paths_and_symlink_destinations_are_denied(
        self,
    ):
        destination = self.root / "installed/v0.12.0-linux"
        for names in (
            ["../escape"],
            ["one.dll", "ONE.dll"],
            ["/absolute"],
            ["C:/escape"],
        ):
            archive = self.root / "bad.zip"
            with ZipFile(archive, "w") as output:
                for name in names:
                    output.writestr(name, b"bad")
            with self.subTest(names=names), self.assertRaises(UserError):
                renderer.install_renderer_archive(archive, destination, version="0.12.0", os_family="linux")
        destination.parent.mkdir(exist_ok=True)
        destination.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(UserError):
            renderer.install_renderer_archive(archive, destination, version="0.12.0", os_family="linux")
        self.assertFalse((self.root / "escape").exists())

    def test_live_http_challenges_are_signed_and_do_not_contain_identity_credentials(
        self,
    ):
        session = self.session()
        challenge = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        connection = http.client.HTTPConnection("127.0.0.1", session.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("POST", session.path, body=renderer._canonical({"challenge": challenge}))
        response = connection.getresponse()
        self.assertEqual(200, response.status)
        content = response.read()
        self.assertNotIn(IDENTITY.encode(), content)
        self.assertNotIn(IDENTITY, session.url)
        body = json.loads(content)
        proof, signed, signature = renderer._envelope(renderer._canonical(body["proof"]))
        session.key.public_key().verify(signature, signed)
        self.assertEqual(challenge, proof["challenge"])
        self.assertEqual(session.session_id, proof["session_id"])
        self.assertEqual(UID, proof["uid"])
        self.assertEqual("e" * 64, proof["artifact_sha256"])
        self.assertLessEqual(proof["expires_at"] - proof["issued_at"], renderer.LEASE_SECONDS)

    def test_browser_proofs_reject_other_origins_and_allow_only_the_configured_origin(
        self,
    ):
        session = self.session()
        session.origin = "http://localhost:12345"
        connection = http.client.HTTPConnection("127.0.0.1", session.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        body = renderer._canonical({"challenge": base64.b64encode(b"c" * 32).decode("ascii")})
        for origin, status in (
            ("https://attacker.example", 403),
            (session.origin, 200),
        ):
            connection.request("POST", session.path, body=body, headers={"Origin": origin})
            response = connection.getresponse()
            self.assertEqual(status, response.status)
            self.assertEqual(
                origin if status == 200 else None,
                response.getheader("Access-Control-Allow-Origin"),
            )
            response.read()
        connection.request("OPTIONS", session.path, headers={"Origin": session.origin})
        response = connection.getresponse()
        self.assertEqual(204, response.status)
        self.assertEqual(session.origin, response.getheader("Access-Control-Allow-Origin"))
        self.assertEqual("POST", response.getheader("Access-Control-Allow-Methods"))
        response.read()

    def test_copied_grants_without_the_dts_launch_key_cannot_start_offline(self):
        original = self.session()
        original.close()
        original.key_path.unlink()
        with patch.object(
            renderer.RendererSession,
            "_request",
            side_effect=renderer.RendererHubUnavailable("offline"),
        ), self.assertRaises(UserError):
            renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})

    def test_offline_relaunch_reuses_private_launch_key_but_creates_a_new_live_session(
        self,
    ):
        first = self.session()
        first.close()
        with patch.object(
            renderer.RendererSession,
            "_request",
            side_effect=renderer.RendererHubUnavailable("offline"),
        ):
            second = renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        self.addCleanup(second.close)
        self.assertEqual(first.launch_key, second.launch_key)
        self.assertNotEqual(first.session_id, second.session_id)
        if os.name != "nt":
            self.assertEqual(0o600, second.key_path.stat().st_mode & 0o777)
            self.assertEqual(0o600, second.grant_path.stat().st_mode & 0o777)

    def test_concurrent_first_launches_share_one_key_and_allow_offline_relaunch(self):
        generate = Ed25519PrivateKey.generate
        overlapping_generation = threading.Barrier(2)

        def synchronized_generate():
            key = generate()
            try:
                overlapping_generation.wait(timeout=2)
            except threading.BrokenBarrierError:
                pass
            return key

        def request(session):
            return self.fixture.grant(session.launch_key, development=session.development)

        def create_session():
            session = renderer.RendererSession(
                self.shell,
                os_family="linux",
                release={"sha256": "e" * 64},
                renew=True,
            )
            self.addCleanup(session.close)
            return session

        with patch.object(renderer.RendererSession, "_request", new=request), patch.object(
            Ed25519PrivateKey, "generate", side_effect=synchronized_generate
        ) as generation, ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create_session) for _ in range(2)]
            first, second = [future.result(timeout=10) for future in futures]
        self.assertEqual(first.launch_key, second.launch_key)
        self.assertEqual(1, generation.call_count)
        first.close()
        second.close()
        with patch.object(
            renderer.RendererSession,
            "_request",
            side_effect=renderer.RendererHubUnavailable("offline"),
        ) as request:
            offline = renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        self.addCleanup(offline.close)
        request.assert_not_called()
        self.assertEqual(first.launch_key, offline.launch_key)

    def test_launch_key_cache_lock_timeout_fails_explicitly(self):
        with patch.object(renderer.RendererSession, "_request") as request, patch.object(
            renderer, "FileLock"
        ) as lock:
            lock.return_value.__enter__.side_effect = renderer.Timeout("cache.lock")
            with self.assertRaisesRegex(UserError, "authorization cache"):
                renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        request.assert_not_called()

    def test_closed_expired_changed_identity_and_changed_computer_sessions_cannot_sign(
        self,
    ):
        challenge = base64.b64encode(b"c" * 32).decode("ascii")
        session = self.session()
        with patch(
            "dt_shell.renderer._identity",
            return_value=("other", SimpleNamespace(uid=UID)),
        ), self.assertRaises(UserError):
            session.proof(challenge)
        with patch("dt_shell_device.get_device_id", return_value="b" * 64), self.assertRaises(UserError):
            session.proof(challenge)
        session.deadline = time.monotonic() - 1
        with self.assertRaises(renderer.RendererGrantExpired):
            session.proof(challenge)
        session.close()
        with self.assertRaises(UserError):
            session.proof(challenge)

    def test_invalid_cache_fails_explicitly_instead_of_silent_online_fallback(self):
        session = self.session()
        session.close()
        session.grant_path.write_text("invalid")
        with patch.object(renderer.RendererSession, "_request") as request, self.assertRaises(UserError):
            renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        request.assert_not_called()

    def test_near_expiry_startup_refreshes_or_retains_only_a_valid_offline_grant(self):
        original = self.session()
        original.close()
        short = self.fixture.grant(original.launch_key, changes={"expires_at": int(time.time()) + 180})
        original.grant_path.write_text(short)
        with patch.object(
            renderer.RendererSession,
            "_request",
            side_effect=renderer.RendererHubUnavailable("offline"),
        ) as request:
            offline = renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        self.addCleanup(offline.close)
        request.assert_called_once()
        self.assertEqual(short, offline.grant)
        offline.close()
        with patch.object(
            renderer.RendererSession,
            "_request",
            side_effect=UserError("permission revoked"),
        ), self.assertRaisesRegex(UserError, "revoked"):
            renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        refreshed = self.session()
        self.assertGreater(refreshed.claims["expires_at"] - time.time(), 300)

    def test_cache_reads_reject_oversized_and_dangling_or_existing_symlinks(self):
        session = self.session()
        session.close()
        session.grant_path.write_bytes(b"x" * 65537)
        with self.assertRaisesRegex(UserError, "size limit"):
            renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        for target in (self.root / "missing", session.key_path):
            session.grant_path.unlink()
            session.grant_path.symlink_to(target)
            with self.subTest(target=target.name), self.assertRaisesRegex(UserError, "symbolic"):
                renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})
        session.grant_path.unlink()
        session.key_path.unlink()
        session.key_path.symlink_to(self.root / "missing-key")
        with self.assertRaisesRegex(UserError, "symbolic"):
            renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})

    def test_hub_explicit_http_denial_is_not_an_offline_outage(self):
        session = self.session()
        session.close()
        for status in (301, 401, 403, 404):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status_code = status
            with patch("dt_shell.renderer.requests.post", return_value=response), self.subTest(status=status):
                with self.assertRaises(UserError) as failure:
                    session._request()
                self.assertNotIsInstance(failure.exception, renderer.RendererHubUnavailable)
        with patch(
            "dt_shell.renderer.requests.post", side_effect=requests.Timeout("offline")
        ), self.assertRaises(renderer.RendererHubUnavailable):
            session._request()
        response.status_code = 200
        response.iter_content.return_value = [b"[]"]
        with patch("dt_shell.renderer.requests.post", return_value=response), self.assertRaisesRegex(
            UserError, "response"
        ):
            session._request()
        response.iter_content.return_value = [b'{"success":false,"messages":["Permission revoked."]}']
        with patch("dt_shell.renderer.requests.post", return_value=response), self.assertRaisesRegex(
            UserError, "revoked"
        ):
            session._request()

    def test_stream_read_timeout_is_reported_as_an_offline_hub_outage(self):
        session = self.session()
        session.close()
        response = requests.Response()
        response.status_code = 200
        response.raw = MagicMock()
        timeout = ReadTimeoutError(None, "renderer-test", "stream interrupted")
        response.raw.read.side_effect = timeout
        response.raw.stream.side_effect = timeout
        with patch("dt_shell.renderer.requests.post", return_value=response), self.assertRaises(
            renderer.RendererHubUnavailable
        ):
            session._request()

    def test_archive_special_files_and_extraction_limits_are_rejected_before_installation(
        self,
    ):
        destination = self.root / "installed/v0.12.0-linux"
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR):
            archive = self.root / "special.zip"
            entry = ZipInfo("special")
            entry.external_attr = (mode | 0o600) << 16
            with ZipFile(archive, "w") as output:
                output.writestr(entry, b"bad")
            with self.subTest(mode=mode), self.assertRaisesRegex(UserError, "file type"):
                renderer.install_renderer_archive(archive, destination, version="0.12.0", os_family="linux")
        oversized = ZipInfo("large")
        oversized.file_size = 10 * 1024**3 + 1
        with patch("dt_shell.renderer.ZipFile") as archive:
            archive.return_value.__enter__.return_value.infolist.return_value = [oversized]
            with self.assertRaisesRegex(UserError, "limits"):
                renderer.install_renderer_archive(
                    self.root / "large.zip",
                    destination,
                    version="0.12.0",
                    os_family="linux",
                )
            archive.return_value.__enter__.return_value.infolist.return_value = [ZipInfo("one")] * 100001
            with self.assertRaisesRegex(UserError, "limits"):
                renderer.install_renderer_archive(
                    self.root / "many.zip",
                    destination,
                    version="0.12.0",
                    os_family="linux",
                )
        self.assertFalse(destination.exists())

    def test_developer_sessions_are_separate_and_daffy_cannot_start_the_ente_feature(
        self,
    ):
        developer = self.session(development=True)
        self.assertEqual(renderer.DEVELOP_CAPABILITY, developer.claims["capability"])
        self.assertLessEqual(developer.claims["expires_at"] - developer.claims["issued_at"], 3600)
        self.shell.profile.distro.name = "daffy"
        with self.assertRaisesRegex(UserError, "exclusive"):
            renderer.RendererSession(self.shell, os_family="linux", release={"sha256": "e" * 64})

    def test_clock_rollback_and_malformed_challenges_do_not_extend_sessions(self):
        session = self.session()
        for challenge in ("bad", "", base64.b64encode(b"short").decode(), None):
            with self.subTest(challenge=challenge), self.assertRaises(UserError):
                session.proof(challenge)
        session.last_wall = time.time() + 60
        with self.assertRaisesRegex(UserError, "backwards"):
            session.proof(base64.b64encode(b"c" * 32).decode())


def write_verifier_vectors(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fixture = RendererFixture(directory)
    launch = Ed25519PrivateKey.generate()
    launch_public = public(launch)
    now = int(time.time())
    tests = []

    def lease(
        name,
        *,
        development=False,
        grant_changes=None,
        proof_changes=None,
        expected=True,
        expected_device=DEVICE,
        expected_artifact="e" * 64,
        issuer=ISSUERS[0],
        at=None,
        delta=0,
        response=None,
    ):
        issued_at = now if at is None else at
        grant = fixture.grant(
            launch_public,
            development=development,
            changes=grant_changes,
            issuer=issuer,
            now=issued_at,
        )
        body = response or fixture.signed_proof(grant, launch, changes=proof_changes, now=issued_at)
        tests.append(
            {
                "kind": "lease",
                "name": name,
                "response": body,
                "accept": expected,
                "development": development,
                "session_id": "d" * 32,
                "challenge": base64.b64encode(b"n" * 32).decode(),
                "device_id": expected_device,
                "artifact": expected_artifact,
                "now": issued_at + delta,
                "expected_expiration": (proof_changes or {}).get("expires_at", issued_at + 30),
            }
        )

    lease("normal plan")
    deadline = int(datetime.datetime(2027, 2, 1, tzinfo=datetime.timezone.utc).timestamp())
    for name, delta, accepted in (("before", 0, True), ("at", 1, False), ("after", 2, False)):
        lease(
            "plan-free access " + name + " the February cutoff",
            at=deadline - 1,
            grant_changes={"base_plan": None, "plan_grace_until": deadline, "expires_at": deadline},
            proof_changes={"expires_at": deadline},
            delta=delta,
            expected=accepted,
        )
    lease("staging plan", issuer=ISSUERS[1])
    lease("staff normal use", grant_changes={"is_staff": True, "base_plan": None})
    lease("superuser normal use", grant_changes={"is_superuser": True, "base_plan": None})
    lease(
        "native WSL device binding",
        proof_changes={"renderer_device_id": "b" * 64},
        expected_device="b" * 64,
    )
    lease("WebGL local DTS binding", expected_device=None)
    lease(
        "developer",
        development=True,
        proof_changes={"artifact_sha256": None},
        expected_artifact=None,
    )
    lease(
        "privileged expiry",
        grant_changes={"is_staff": True, "expires_at": now},
        expected=False,
    )
    lease("offline permission expiry", delta=86401, expected=False)
    lease("DTS stopped and live proof expired", delta=31, expected=False)
    for field, value in (
        ("format", True),
        ("uid", True),
        ("uid", 0),
        ("is_staff", 1),
        ("is_superuser", "false"),
        ("renewable", True),
        ("audience", "duckietown-shell-developer"),
        ("capability", "use:ente"),
        ("base_plan", "instructor"),
        ("base_plan", {}),
        ("identity_sha256", "bad"),
        ("device_id", "bad"),
        ("launch_key", "b" * 64),
        ("extra", True),
        ("issued_at", now + 61),
        ("expires_at", now + 86401),
        ("entitlement_expiration", now + 60),
    ):
        lease(
            "invalid grant " + field + repr(value),
            grant_changes={field: value},
            expected=False,
        )
    for field, value in (
        ("session_id", "f" * 32),
        ("challenge", base64.b64encode(b"x" * 32).decode()),
        ("grant_sha256", "f" * 64),
        ("uid", UID + 1),
        ("identity_sha256", "f" * 64),
        ("device_id", "b" * 64),
        ("renderer_device_id", "b" * 64),
        ("artifact_sha256", "b" * 64),
        ("issued_at", now + 6),
        ("expires_at", now),
        ("expires_at", now + 31),
        ("extra", True),
    ):
        lease(
            "invalid live proof " + field + repr(value),
            proof_changes={field: value},
            expected=False,
        )
    lease("missing proof", response='{"grant":"missing"}', expected=False)
    lease("copied grant on another computer", expected_device="b" * 64, expected=False)
    for platform in ("linux", "windows", "macos", "webgl"):
        root = fixture.release(platform)
        manifest = (root / renderer.RENDERER_MANIFEST).read_text()
        tests.append(
            {
                "kind": "manifest",
                "name": "signed " + platform,
                "accept": True,
                "manifest": manifest,
                "version": "0.12.0",
                "platform": platform,
                "root": str(root),
            }
        )
        tests.append(
            {
                "kind": "manifest",
                "name": "wrong requested version " + platform,
                "accept": False,
                "manifest": manifest,
                "version": "0.13.0",
                "platform": platform,
                "root": str(root),
            }
        )
    altered = fixture.release(name="altered")
    (altered / "duckiematrix.x86_64").write_bytes(b"tampered")
    tests.append(
        {
            "kind": "manifest",
            "name": "altered renderer executable",
            "accept": False,
            "manifest": (altered / renderer.RENDERER_MANIFEST).read_text(),
            "version": "0.12.0",
            "platform": "linux",
            "root": str(altered),
        }
    )
    for endpoint, accepted in (
        ("http://127.0.0.1:1234/renderer/" + "d" * 32 + "/proof", True),
        ("http://[::1]:1234/renderer/" + "d" * 32 + "/proof", True),
        ("https://hub.duckietown.com/api/v1/auth/token/renderer/", False),
        ("http://attacker.example/renderer/" + "d" * 32 + "/proof", False),
        ("http://127.0.0.1:1234/renderer/" + "d" * 32 + "/proof?token=secret", False),
        ("http://user:password@127.0.0.1:1234/renderer/" + "d" * 32 + "/proof", False),
        ("", False),
    ):
        tests.append(
            {
                "kind": "endpoint",
                "name": "endpoint " + endpoint,
                "endpoint": endpoint,
                "accept": accepted,
            }
        )
    machine = "12345678123456781234567812345678"
    for value in (machine, machine.upper(), "12345678-1234-5678-1234-567812345678"):
        tests.append(
            {
                "kind": "fingerprint",
                "name": "normalized machine identity " + value,
                "accept": True,
                "machine_id": value,
                "fingerprint": hashlib.sha256(("duckietown-ente-device-v1:" + machine).encode()).hexdigest(),
            }
        )
    for name, wall_delta, monotonic, accepted in (
        ("live before deadline", 29, 129, True),
        ("exact signed expiry", 30, 129.1, False),
        ("exact monotonic expiry", 29, 130, False),
        ("clock rollback", -6, 101, False),
        ("small tolerated correction does not extend deadline", -4, 130, False),
    ):
        tests.append(
            {
                "kind": "clock",
                "name": name,
                "accept": accepted,
                "wall": now,
                "monotonic": 100,
                "expires_at": now + 30,
                "check_wall": now + wall_delta,
                "check_monotonic": monotonic,
            }
        )
    path = directory / "vectors.json"
    path.write_bytes(
        renderer._canonical(
            {
                "issuers": fixture.issuers,
                "release_key": fixture.release_public,
                "tests": tests,
            }
        )
    )
    return path


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--vectors":
        print(write_verifier_vectors(Path(sys.argv[2])))
    else:
        unittest.main()
