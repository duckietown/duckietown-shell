import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dt_shell_tests.test_engine import EngineFixture
from dt_shell_tests import test_release_tools as wheel_tests


ROOT = Path(__file__).resolve().parents[2]


class EngineReleaseTests(unittest.TestCase):
    def setUp(self):
        authority = wheel_tests.ReleaseToolTests()
        authority.setUp()
        self.addCleanup(authority.doCleanups)
        self.root = authority.directory
        self.fixture = EngineFixture(self.root)
        environment = patch.dict(os.environ, {
            "DTM_ENGINE_RELEASE_PUBLIC_KEY": self.fixture.release_public,
            "DTM_ENGINE_PUBLIC_KEYS": json.dumps(self.fixture.issuers),
        })
        environment.start()
        self.addCleanup(environment.stop)
        spec = importlib.util.spec_from_file_location("test_engine_release_tools", ROOT / "tools/engine_release.py")
        assert spec is not None and spec.loader is not None
        self.tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tools)
        self.key = self.root / "engine.pem"
        descriptor = os.open(self.key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(self.fixture.release_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
            ))

    def test_seal_signs_the_engine_inventory_with_exact_trust(self):
        root = self.fixture.release()
        result = self.tools.seal(root, version="1.2.3", platform="linux", key=self.tools.signing_key(self.key))
        self.assertEqual("duckiematrix-engine-release", result["audience"])
        self.assertEqual("1.2.3", result["version"])
        self.assertEqual({"release": self.fixture.release_public, "issuers": self.fixture.issuers}, result["trust"])
        self.assertEqual(64, len(result["sha256"]))

    def test_plaintext_protected_modules_cannot_be_sealed_as_production(self):
        root = self.fixture.release()
        (root / "packages/duckiematrix_engine/bootstrap.py").write_text("print('fallback')\n")
        with self.assertRaisesRegex(self.tools.runtime.EngineAuthorizationError, "without source fallbacks"):
            self.tools.seal(root, version="1.2.3", platform="linux", key=self.fixture.release_key)

    def test_wrong_artifact_key_is_rejected(self):
        other = Ed25519PrivateKey.generate()
        self.key.write_bytes(other.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.tools.signing_key(self.key)

    def test_catalog_cli_emits_a_signed_immutable_engine_catalog(self):
        images = self.root / "images.json"
        record = {
            "reference": "duckietown/dt-duckiematrix@sha256:" + "b" * 64,
            "config_sha256": "c" * 64, "runtime_sha256": "d" * 64,
        }
        images.write_text(json.dumps({"amd64": record, "arm64v8": record}))
        output = self.root / "engines.json"
        args = ["engine_release.py", "catalog", str(images), "--version", "1.2.3",
                "--key", str(self.key), "--output", str(output)]
        with patch.object(sys, "argv", args), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.tools.main()
        result = self.tools.runtime.verify_image_catalog(output.read_bytes(), release_key=self.fixture.release_public)
        self.assertEqual({"format", "audience", "distribution", "version", "images"}, set(result))
        self.assertEqual("duckiematrix-engine-images", result["audience"])
        self.assertEqual({"amd64", "arm64v8"}, set(result["images"]))
        self.assertEqual("1.2.3", json.loads(stdout.getvalue())["version"])
