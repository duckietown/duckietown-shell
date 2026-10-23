import base64
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from dt_shell import renderer, viewer, viewer_runtime as runtime
from dt_shell.exceptions import UserError
from dt_shell_tests.test_renderer import DEVICE, IDENTITY, ISSUERS, UID, RendererFixture


class ViewerFixture(RendererFixture):
    def grant(self, key, *, app="image_viewer", development=False, changes=None, **kwargs):
        return super().grant(
            key, development=development,
            changes={
                "audience": runtime.AUDIENCE,
                "capability": ("develop:" if development else "use:") + runtime.AUDIENCE,
                "app": app, "distribution": "ente", **(changes or {}),
            }, **kwargs,
        )

    def context(self, *, app="image_viewer", development=False, desktop=False):
        return {
            "app": app, "distribution": "ente", "endpoint": "http://localhost:54321/app/",
            "backend": "e" * 64, "backend_image": "f" * 64,
            "desktop": "c" * 64 if desktop else None,
            "desktop_version": "1.2.3" if desktop else None,
            "devices": {"backend": DEVICE, "desktop": DEVICE},
            "tickets": {
                role: hashlib.sha256((digit * 64).encode()).hexdigest()
                for role, digit in (("ready", "1"), ("desktop", "2"), ("browser", "3"))
            },
            "development": development,
        }

    def release(self, name="desktop", *, platform="linux"):
        root = self.root / name
        root.mkdir()
        entry = root / "viewer"
        entry.write_bytes(b"native fixture, not a production app")
        entry.chmod(0o755)
        manifest = {
            "format": 1, "audience": "duckietown-viewer-release", "kind": "desktop",
            "distribution": "ente", "version": "1.2.3", "platform": platform,
            "entrypoint": "viewer", "files": runtime.inventory(root),
            "trust": {"release": self.release_public, "issuers": self.issuers},
        }
        (root / runtime.MANIFEST).write_bytes(self.sign(manifest))
        return root

    def sign(self, claims):
        return runtime.canonical(renderer._signed(runtime.canonical(claims), self.release_key))


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="viewer-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = ViewerFixture(self.root)
        self.shell = SimpleNamespace(profile=SimpleNamespace(
            distro=SimpleNamespace(name="ente"),
            database=lambda name: SimpleNamespace(yaml=str(self.root / f"{name}.yaml")),
        ))
        for mock in (
            patch("dt_shell.viewer._trust", return_value=(self.fixture.release_public, self.fixture.issuers)),
            patch("dt_shell.renderer._identity", return_value=(IDENTITY, SimpleNamespace(uid=UID))),
            patch("dt_shell.renderer.DTHUB_URL", ISSUERS[0]),
            patch("dt_shell_device.get_device_parameters", return_value={"device_id": DEVICE, "device_hostname": "computer"}),
            patch("dt_shell_device.get_device_id", return_value=DEVICE),
            patch("dt_shell_device.get_renderer_device_id", return_value=DEVICE),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def session(self, *, app="image_viewer", development=False, desktop=False, request=None):
        fixture = self.fixture

        def issue(session):
            return fixture.grant(session.launch_key, app=session.app, development=session.development)

        with patch.object(viewer.ViewerSession, "_request", new=request or issue):
            session = viewer.ViewerSession(
                self.shell, app=app, os_family="linux",
                context=fixture.context(app=app, development=development, desktop=desktop),
            )
        self.addCleanup(session.close)
        return session

    def test_signed_live_session_is_separate_from_renderer_and_has_no_identity_handoff(self):
        session = self.session()
        handoff = self.root / "backend.json"
        session.write_handoff(handoff, consumer="backend", ticket="1" * 64)
        raw = handoff.read_bytes()
        self.assertNotIn(IDENTITY.encode(), raw)
        self.assertNotIn(b"PRIVATE KEY", raw)
        if os.name != "nt":
            self.assertEqual(0o600, handoff.stat().st_mode & 0o777)
        lease = runtime.ViewerLease(runtime.read_handoff(handoff), issuer_keys=self.fixture.issuers)
        lease.current()
        self.assertEqual(runtime.PROOF_AUDIENCE, lease.claims["audience"])
        self.assertEqual("backend", lease.claims["consumer"])
        self.assertLessEqual(lease.wall_deadline - time.time(), 30)

    def test_broker_requires_private_handoff_and_specific_consumer(self):
        session = self.session()
        connection = http.client.HTTPConnection("127.0.0.1", session.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        connection.request("POST", session.path, body=runtime.canonical({"challenge": "x"}))
        response = connection.getresponse()
        self.assertEqual(403, response.status)
        response.read()
        connection.request(
            "POST", session.path, body=runtime.canonical({"challenge": "x", "consumer": "browser"}),
            headers=session._broker_headers(),
        )
        response = connection.getresponse()
        self.assertEqual(403, response.status)
        response.read()

    def test_replayed_challenge_role_app_endpoint_device_and_scope_are_rejected(self):
        session = self.session()
        challenge = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        response = session.proof(challenge, consumer="backend")
        parameters = dict(
            issuer_keys=self.fixture.issuers, challenge=challenge,
            session_id=session.session_id, consumer="backend", context=session.context,
        )
        runtime.validate_proof(response, **parameters)
        for changed in (
            {"challenge": base64.b64encode(secrets.token_bytes(32)).decode("ascii")},
            {"consumer": "desktop"}, {"session_id": "c" * 32},
            {"context": {**session.context, "endpoint": "http://localhost:12345/app/"}},
            {"context": {**session.context, "app": "led_controller"}},
            {"device_id": "b" * 64},
        ):
            with self.subTest(changed=changed), self.assertRaises(runtime.ViewerAuthorizationError):
                runtime.validate_proof(response, **{**parameters, **changed})
        for changes in (
            {"audience": renderer.GRANT_AUDIENCE},
            {"capability": renderer.USE_CAPABILITY}, {"capability": "develop:dts"},
            {"app": "led_controller"}, {"distribution": "daffy"},
            {"issuer": "https://attacker.example"}, {"renewable": True},
            {"base_plan": "instructor"}, {"uid": True},
            {"expires_at": int(time.time()) + 86401},
        ):
            with self.subTest(changes=changes), self.assertRaises(runtime.ViewerAuthorizationError):
                runtime.validate_grant(
                    self.fixture.grant(session.launch_key, changes=changes),
                    issuer_keys=self.fixture.issuers, app=session.app, development=False,
                )

    def test_expiry_rollback_and_dts_exit_cannot_extend_a_lease(self):
        session = self.session()
        path = self.root / "backend.json"
        session.write_handoff(path, consumer="backend", ticket="1" * 64)
        lease = runtime.ViewerLease(runtime.read_handoff(path), issuer_keys=self.fixture.issuers)
        session.close()
        with self.assertRaises(runtime.ViewerBrokerUnavailable):
            lease.renew()
        with patch.object(runtime.time, "monotonic", return_value=lease.deadline):
            with self.assertRaises(runtime.ViewerGrantExpired):
                lease.current()
        with patch.object(runtime.time, "time", return_value=lease.last_wall - 6):
            with self.assertRaisesRegex(runtime.ViewerAuthorizationError, "backwards"):
                lease.current()

    def test_offline_relaunch_reuses_only_a_valid_grant_for_the_same_app(self):
        session = self.session()
        key, grant = session.launch_key, session.grant
        session.close()

        def no_hub(_):
            self.fail("A valid cached per-app grant should permit offline relaunch.")

        relaunched = self.session(request=no_hub)
        self.assertEqual((key, grant), (relaunched.launch_key, relaunched.grant))
        other = self.session(app="led_controller")
        self.assertNotEqual(relaunched.grant_path, other.grant_path)

    def test_developer_grants_require_current_signed_privileges_and_one_hour_limit(self):
        session = self.session(development=True)
        self.assertEqual(3600, session.claims["expires_at"] - session.claims["issued_at"])
        for changes in ({"is_staff": False}, {"expires_at": session.claims["issued_at"] + 3601}):
            with self.assertRaises(runtime.ViewerAuthorizationError):
                runtime.validate_grant(
                    self.fixture.grant(session.launch_key, development=True, changes=changes),
                    issuer_keys=self.fixture.issuers, app=session.app, development=True,
                )

    def test_release_inventory_rejects_tampering_extra_files_and_renderer_manifest(self):
        root = self.fixture.release()
        keys = dict(release_key=self.fixture.release_public, issuer_keys=self.fixture.issuers)
        runtime.verify_release(root, **keys)
        (root / "injected.js").write_bytes(b"modified")
        with self.assertRaises(runtime.ViewerAuthorizationError):
            runtime.verify_release(root, **keys)
        (root / "injected.js").unlink()
        (root / "viewer").write_bytes(b"altered")
        with self.assertRaises(runtime.ViewerAuthorizationError):
            runtime.verify_release(root, **keys)

    def test_safe_atomic_install_preserves_the_previous_release_on_tampered_or_unsafe_input(self):
        root = self.fixture.release()
        archive = self.root / "release.zip"
        with ZipFile(archive, "w") as stream:
            for path in root.iterdir():
                stream.write(path, path.name)
        target = self.root / "install" / "v1.2.3-linux"
        args = dict(
            release_key=self.fixture.release_public, issuer_keys=self.fixture.issuers,
            version="1.2.3", platform="linux",
        )
        runtime.install_archive(archive, target, **args)
        original = (target / "viewer").read_bytes()
        with ZipFile(archive, "a") as stream:
            stream.writestr("../escape", "not allowed")
        with self.assertRaises(runtime.ViewerAuthorizationError):
            runtime.install_archive(archive, target, **args)
        self.assertEqual(original, (target / "viewer").read_bytes())
        self.assertFalse((target.parent / "escape").exists())

    def test_duplicate_json_nan_unknown_apps_and_forged_distribution_are_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(runtime.ViewerAuthorizationError):
                runtime.decode_json(raw)
        for context in (
            {**self.fixture.context(), "app": "unknown"},
            {**self.fixture.context(), "distribution": "daffy"},
            {**self.fixture.context(), "endpoint": "http://localhost:8000/app/?bypass=1"},
        ):
            with self.assertRaises(runtime.ViewerAuthorizationError):
                runtime.validate_context(context)

    def test_explicit_denial_and_invalid_grants_invalidate_cached_permission(self):
        session = self.session()
        path = session.grant_path
        self.assertTrue(path.exists())
        with patch.object(renderer.RendererSession, "_request", side_effect=UserError("Hub denied")):
            with self.assertRaises(UserError):
                session._request()
        self.assertFalse(path.exists())
        path.write_text(session.grant)
        with self.assertRaises(UserError):
            session._validate("not a grant")
        self.assertFalse(path.exists())

    def test_forwarded_proofs_are_app_host_and_privilege_bound_not_a_global_plan_exemption(self):
        from dt_shell.authorization import require_ente_plan

        session = self.session(desktop=True)
        path = self.root / "desktop.json"
        session.write_handoff(path, consumer="desktop", ticket="2" * 64)
        command = SimpleNamespace(command_set=SimpleNamespace(name="ente"), selector="duckiebot.image_viewer")
        with patch.dict(os.environ, {viewer.FORWARDED_HANDOFF_ENV: str(path)}):
            lease = viewer.forwarded_lease("image_viewer")
            lease.current()
            with patch("dt_shell.authorization._identity", side_effect=UserError("ordinary gate")) as identity:
                require_ente_plan(self.shell, command)
                identity.assert_not_called()
                command.selector = "matrix.run"
                with self.assertRaisesRegex(UserError, "ordinary gate"):
                    require_ente_plan(self.shell, command)
            with self.assertRaises(UserError):
                viewer.forwarded_lease("led_controller")
            with patch("dt_shell_device.get_device_id", return_value="b" * 64), self.assertRaises(UserError):
                viewer.forwarded_lease("image_viewer")
            with self.assertRaisesRegex(UserError, "developer permission"):
                viewer.authorize_install(self.shell, "image_viewer", development=True)

    def test_consumer_tickets_and_invalid_installed_releases_fail_explicitly(self):
        session = self.session(desktop=True)
        path = self.root / "desktop.json"
        session.write_handoff(path, consumer="desktop", ticket="2" * 64)
        data = runtime.decode_json(path.read_bytes())
        data["ticket"] = "1" * 64
        path.write_bytes(runtime.canonical(data))
        with self.assertRaisesRegex(runtime.ViewerAuthorizationError, "ticket"):
            runtime.read_handoff(path)
        root = self.fixture.release()
        (root / "viewer").write_bytes(b"tampered")
        with self.assertRaises(UserError):
            viewer.verify_viewer_release(root)
