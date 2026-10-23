import base64
import copy
import hashlib
import http.client
import os
from pathlib import Path
import secrets
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dt_shell import engine, engine_runtime as runtime, renderer, viewer_runtime
from dt_shell.exceptions import UserError
from dt_shell_tests.test_renderer import DEVICE, IDENTITY, ISSUERS, UID, RendererFixture


class EngineFixture(RendererFixture):
    def grant(self, key, *, development=False, changes=None, **kwargs):
        return super().grant(key, development=development, changes={
            "audience": runtime.AUDIENCE,
            "capability": ("develop:" if development else "use:") + runtime.AUDIENCE,
            **(changes or {}),
        }, **kwargs)

    def context(self, *, development=False):
        return {
            "distribution": "ente", "runtime": "e" * 64, "image": "f" * 64,
            "device_id": DEVICE, "development": development,
        }

    def signed(self, claims):
        return renderer._canonical(renderer._signed(renderer._canonical(claims), self.release_key))

    def release(self, name="engine"):
        root = self.root / name
        package = root / "packages/duckiematrix_engine"
        package.mkdir(parents=True)
        for module in ("bootstrap", "engine"):
            (package / f"{module}.fixture.so").write_bytes(b"compiled fixture, not a real binary")
        claims = {
            "format": 1, "audience": "duckiematrix-engine-release", "kind": "engine",
            "distribution": "ente", "version": "1.0.0", "platform": "linux",
            "entrypoint": "packages/duckiematrix_engine",
            "files": viewer_runtime.inventory(root, manifest=runtime.MANIFEST),
            "trust": {"release": self.release_public, "issuers": self.issuers},
        }
        (root / runtime.MANIFEST).write_bytes(self.signed(claims))
        return root


class EngineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="engine-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = EngineFixture(self.root)
        self.shell = SimpleNamespace(profile=SimpleNamespace(
            distro=SimpleNamespace(name="ente"),
            database=lambda name: SimpleNamespace(yaml=str(self.root / f"{name}.yaml")),
        ))
        for mock in (
            patch("dt_shell.engine._trust", return_value=(self.fixture.release_public, self.fixture.issuers)),
            patch("dt_shell.renderer._identity", return_value=(IDENTITY, SimpleNamespace(uid=UID))),
            patch("dt_shell.renderer.DTHUB_URL", ISSUERS[0]),
            patch("dt_shell_device.get_device_parameters", return_value={"device_id": DEVICE, "device_hostname": "computer"}),
            patch("dt_shell_device.get_device_id", return_value=DEVICE),
            patch("dt_shell_device.get_renderer_device_id", return_value=DEVICE),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def session(self, *, context=None, request=None):
        fixture = self.fixture

        def issue(session):
            return fixture.grant(session.launch_key, development=session.development)

        with patch.object(engine.EngineSession, "_request", new=request or issue):
            session = engine.EngineSession(self.shell, context=context or fixture.context())
        self.addCleanup(session.close)
        return session

    def lease(self, session):
        path = self.root / f"{session.session_id}.json"
        session.write_handoff(path)
        return runtime.EngineLease(runtime.read_handoff(path), issuer_keys=self.fixture.issuers), path

    def test_live_engine_scope_and_private_handoff_do_not_expose_identity_or_launch_private_key(self):
        session = self.session()
        lease, path = self.lease(session)
        lease.current()
        self.assertEqual(runtime.PROOF_AUDIENCE, lease.claims["audience"])
        self.assertLessEqual(lease.wall_deadline - time.time(), 30)
        self.assertNotIn(IDENTITY.encode(), path.read_bytes())
        self.assertNotIn(b"PRIVATE KEY", path.read_bytes())
        if os.name != "nt":
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            path.chmod(0o644)
            with self.assertRaises(runtime.EngineAuthorizationError):
                runtime.read_handoff(path)

    def test_broker_denies_missing_secret_and_other_consumers(self):
        session = self.session()
        connection = http.client.HTTPConnection("127.0.0.1", session.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        for headers, consumer in (({}, "engine"), (session._broker_headers(), "backend")):
            connection.request("POST", session.path, viewer_runtime.canonical({
                "challenge": base64.b64encode(secrets.token_bytes(32)).decode("ascii"), "consumer": consumer,
            }), headers)
            response = connection.getresponse()
            self.assertEqual(403, response.status)
            response.read()

    def test_handoff_creation_never_overwrites_an_existing_file_or_symlink(self):
        session = self.session()
        path = self.root / "existing.json"
        path.write_bytes(b"unrelated file")
        link = self.root / "symlink.json"
        link.symlink_to(path)
        dangling = self.root / "dangling.json"
        dangling.symlink_to(self.root / "missing.json")
        for destination in (path, link, dangling):
            with self.subTest(destination=destination.name):
                with self.assertRaisesRegex(UserError, "new private Engine handoff"):
                    session.write_handoff(destination)
        self.assertEqual(b"unrelated file", path.read_bytes())
        self.assertTrue(link.is_symlink())
        self.assertTrue(dangling.is_symlink())

    def test_wrong_scope_identity_device_grace_lifetime_and_development_are_rejected(self):
        session = self.session()
        for changes in (
            {"audience": "duckietown-viewer"}, {"audience": renderer.GRANT_AUDIENCE},
            {"capability": "use:ente"}, {"capability": "develop:dts"},
            {"base_plan": "instructor"}, {"uid": True}, {"renewable": True},
            {"expires_at": int(time.time()) + 86401},
            {"plan_grace_until": int(time.time()) + 100},
            {"device_id": "bad"}, {"launch_key": "bad"},
        ):
            with self.subTest(changes=changes), self.assertRaises(runtime.EngineAuthorizationError):
                runtime.validate_grant(
                    self.fixture.grant(session.launch_key, changes=changes),
                    issuer_keys=self.fixture.issuers, development=False,
                )
        with self.assertRaises(runtime.EngineAuthorizationError):
            runtime.validate_grant(session.grant, issuer_keys=self.fixture.issuers, development=True)
        for field in ("uid", "device_id", "identity_sha256", "launch_key", "issuer"):
            with self.subTest(field=field), self.assertRaises(runtime.EngineAuthorizationError):
                runtime.validate_grant(
                    session.grant, issuer_keys=self.fixture.issuers, development=False, expected={field: "wrong"},
                )

    def test_proof_replay_context_consumer_and_device_substitution_are_rejected(self):
        session = self.session()
        challenge = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        response = session.proof(challenge, consumer="engine")
        parameters = {
            "issuer_keys": self.fixture.issuers, "challenge": challenge,
            "session_id": session.session_id, "consumer": "engine", "context": session.context,
        }
        runtime.validate_proof(response, **parameters)
        for changed in (
            {"challenge": base64.b64encode(secrets.token_bytes(32)).decode("ascii")},
            {"session_id": "b" * 32}, {"consumer": "backend"}, {"device_id": "b" * 64},
            {"context": {**session.context, "image": "c" * 64}},
            {"context": {**session.context, "runtime": "c" * 64}},
            {"context": {**session.context, "development": True}},
        ):
            with self.subTest(changed=changed), self.assertRaises(runtime.EngineAuthorizationError):
                runtime.validate_proof(response, **{**parameters, **changed})

    def test_dts_exit_expiry_and_clock_rollback_cannot_extend_the_lease(self):
        session = self.session()
        lease, _ = self.lease(session)
        session.close()
        with self.assertRaises(runtime.EngineBrokerUnavailable):
            lease.renew()
        with patch.object(viewer_runtime.time, "monotonic", return_value=lease.deadline):
            with self.assertRaises(runtime.EngineGrantExpired):
                lease.current()
        with patch.object(viewer_runtime.time, "time", return_value=lease.last_wall - 6):
            with self.assertRaises(runtime.EngineAuthorizationError):
                lease.current()

    def test_offline_valid_cache_is_reused_but_explicit_denials_are_not_fallbacks(self):
        self.session()

        def denied(_session):
            raise UserError("Engine access denied")

        with patch.object(engine.EngineSession, "_request", new=denied):
            cached = engine.EngineSession(self.shell, context=self.fixture.context())
        self.addCleanup(cached.close)
        cached.grant_path.unlink()
        with patch.object(engine.EngineSession, "_request", new=denied):
            with self.assertRaisesRegex(UserError, "access denied"):
                engine.EngineSession(self.shell, context=self.fixture.context())

    def test_signed_inventory_rejects_modified_added_files_and_python_fallbacks(self):
        root = self.fixture.release()
        arguments = {"release_key": self.fixture.release_public, "issuer_keys": self.fixture.issuers}
        runtime.verify_release(root, **arguments)
        path = root / "packages/duckiematrix_engine/engine.fixture.so"
        path.write_bytes(b"modified")
        with self.assertRaises(runtime.EngineAuthorizationError):
            runtime.verify_release(root, **arguments)
        root = self.fixture.release("source-fallback")
        (root / "packages/duckiematrix_engine/bootstrap.py").write_text("raise SystemExit(0)\n")
        with self.assertRaises(runtime.EngineAuthorizationError):
            runtime.verify_release(root, **arguments)

    def test_catalog_requires_engine_scope_official_repository_and_immutable_identity(self):
        record = {
            "reference": "duckietown/dt-duckiematrix@sha256:" + "b" * 64,
            "config_sha256": "c" * 64, "runtime_sha256": "d" * 64,
        }
        claims = {
            "format": 1, "audience": "duckiematrix-engine-images", "distribution": "ente",
            "version": "1.0.0", "images": {"amd64": record},
        }
        runtime.verify_image_catalog(self.fixture.signed(claims), release_key=self.fixture.release_public)
        for changed in (
            {"audience": "duckietown-viewer-backends"}, {"distribution": "daffy"},
            {"images": {"amd64": {**record, "reference": "duckietown/dt-duckiematrix:ente-amd64"}}},
            {"images": {"amd64": {**record, "reference": record["reference"].replace("dt-duckiematrix", "dt-duckietown-viewer")}}},
        ):
            with self.subTest(changed=changed), self.assertRaises(runtime.EngineAuthorizationError):
                runtime.verify_image_catalog(self.fixture.signed({**claims, **changed}), release_key=self.fixture.release_public)

    def test_normal_and_developer_caches_are_separate_and_daffy_cannot_start_engine_sessions(self):
        normal = self.session()
        developer = self.session(context=self.fixture.context(development=True))
        self.assertNotEqual(normal.grant_path, developer.grant_path)
        self.assertEqual("develop:duckiematrix-engine", developer.claims["capability"])
        self.shell.profile.distro.name = "daffy"
        with self.assertRaisesRegex(UserError, "exclusive"):
            self.session()

    def test_production_inventory_rejects_cached_protected_python_fallbacks(self):
        root = self.fixture.release()
        cache = root / "packages/duckiematrix_engine/__pycache__"
        cache.mkdir()
        (cache / "engine.cpython-312.pyc").write_bytes(b"cached fallback")
        raw = (root / runtime.MANIFEST).read_bytes()
        claims = viewer_runtime.envelope(raw)[0]
        claims["files"] = viewer_runtime.inventory(root, manifest=runtime.MANIFEST)
        (root / runtime.MANIFEST).write_bytes(self.fixture.signed(claims))
        with self.assertRaisesRegex(runtime.EngineAuthorizationError, "without source fallbacks"):
            runtime.verify_release(root, release_key=self.fixture.release_public, issuer_keys=self.fixture.issuers)

    def test_missing_handoff_denies_before_native_trust_or_engine_imports(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(runtime, "native_trust") as trust:
            with self.assertRaisesRegex(runtime.EngineAuthorizationError, "live authorized DTS"):
                runtime.authorize_engine(self.root)
        trust.assert_not_called()

    def test_developer_authorization_starts_monitor_before_engine_initialization(self):
        session = self.session(context=self.fixture.context(development=True))
        _, path = self.lease(session)
        with patch.dict(os.environ, {runtime.HANDOFF_ENV: str(path)}), patch.object(
            runtime, "native_trust", return_value=(self.fixture.release_public, self.fixture.issuers),
        ):
            authorization = runtime.authorize_engine(self.root)
        self.addCleanup(authorization.close)
        self.assertTrue(authorization.thread.is_alive())
        runtime.current_authorization(self.root)
        with self.assertRaises(runtime.EngineAuthorizationError):
            runtime.current_authorization(self.root / "other")
        authorization.close()
        with self.assertRaises(runtime.EngineAuthorizationError):
            runtime.current_authorization(self.root)
