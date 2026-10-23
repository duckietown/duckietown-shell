import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_tools", ROOT / "tools/release.py"
)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dts-release-tools-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.key = Ed25519PrivateKey.generate()
        self.public = (
            self.key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )
        self.version = release.current_version()
        self.commands_key = Ed25519PrivateKey.generate()
        self.commands_public = (
            self.commands_key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )
        self.developer_keys = {
            issuer: Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
            for issuer in (
                "https://hub.duckietown.com",
                "https://staging-hub.duckietown.com",
            )
        }
        self.renderer_keys = {
            issuer: public_key.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ).hex()
            for issuer, public_key in (
                (issuer, Ed25519PrivateKey.generate().public_key())
                for issuer in self.developer_keys
            )
        }
        self.renderer_release_public = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex()
        self.viewer_release_public = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex()
        self.viewer_keys = {
            issuer: Ed25519PrivateKey.generate().public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ).hex() for issuer in self.developer_keys
        }
        self.engine_release_public = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex()
        self.engine_keys = {
            issuer: Ed25519PrivateKey.generate().public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ).hex() for issuer in self.developer_keys
        }
        environment = patch.dict(
            os.environ,
            {
                "DTS_RELEASE_PUBLIC_KEY": self.public,
                "DTS_COMMANDS_PUBLIC_KEY": self.commands_public,
                "DTS_DEVELOPER_PUBLIC_KEYS": json.dumps(self.developer_keys),
                "DTM_RELEASE_PUBLIC_KEY": self.renderer_release_public,
                "DTM_RENDERER_PUBLIC_KEYS": json.dumps(self.renderer_keys),
                "DTV_RELEASE_PUBLIC_KEY": self.viewer_release_public,
                "DTV_AUTH_PUBLIC_KEYS": json.dumps(self.viewer_keys),
                "DTM_ENGINE_RELEASE_PUBLIC_KEY": self.engine_release_public,
                "DTM_ENGINE_PUBLIC_KEYS": json.dumps(self.engine_keys),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

    def wheel(self, python="cp312", platform="linux_aarch64", extra=None, version=None):
        version = version or self.version
        tag = f"{python}-{python}-{platform}"
        path = self.directory / f"duckietown_shell-{version}-{tag}.whl"
        info = f"duckietown_shell-{version}.dist-info"
        data = {
            info
            + "/METADATA": (
                f"Metadata-Version: 2.1\nName: duckietown-shell\nVersion: {version}\n"
                "Requires-Python: >=3.10,<3.13\n"
            ).encode("ascii"),
            info
            + "/WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n".encode(
                "ascii"
            ),
            info
            + "/entry_points.txt": b"[console_scripts]\ndts = dt_shell_release:launch\n",
            info + "/RECORD": b"",
            "dt_shell/__init__.py": b"",
            "dt_shell_cli/__init__.py": b"",
            "dt_shell/assets/requirements.txt": b"cryptography\n",
            "dt_shell/embedded/command_descriptions.yaml": b"version: {}\n",
        }
        suffix = ".pyd" if platform.startswith("win_") else ".so"
        for module in (*release.PROTECTED_MODULES, "dt_shell_release"):
            data[module.replace(".", "/") + "." + python + suffix] = (
                module
                + self.public
                + self.commands_public
                + json.dumps(self.developer_keys, sort_keys=True, separators=(",", ":"))
                + self.renderer_release_public
                + json.dumps(self.renderer_keys, sort_keys=True, separators=(",", ":"))
                + self.viewer_release_public
                + json.dumps(self.viewer_keys, sort_keys=True, separators=(",", ":"))
                + self.engine_release_public
                + json.dumps(self.engine_keys, sort_keys=True, separators=(",", ":"))
            ).encode("ascii")
        data.update(extra or {})
        with ZipFile(path, "w") as archive:
            for name, value in data.items():
                archive.writestr(name, value)
        return path

    def test_signed_native_wheel_verifies_and_record_is_regenerated(self):
        path = self.wheel()
        release.seal(path, self.version, self.key)
        release.verify(path, self.version)
        with ZipFile(path) as archive:
            self.assertIn(release.MANIFEST_NAME, archive.namelist())
            self.assertEqual(64, len(archive.read(release.SIGNATURE_NAME)))
            private = self.key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            self.assertFalse(
                any(private in archive.read(name) for name in archive.namelist())
            )

    def test_unsigned_wheel_cannot_be_verified(self):
        with self.assertRaisesRegex(ValueError, "unsigned"):
            release.verify(self.wheel(), self.version)

    def test_modified_payload_cannot_be_verified(self):
        path = self.wheel()
        release.seal(path, self.version, self.key)
        with ZipFile(path) as archive:
            data = {name: archive.read(name) for name in archive.namelist()}
        data["dt_shell/__init__.py"] += b"changed"
        with ZipFile(path, "w") as archive:
            for name, content in data.items():
                archive.writestr(name, content)
        with self.assertRaisesRegex(ValueError, "signed manifest"):
            release.verify(path, self.version)

    def test_protected_source_and_bytecode_fallbacks_are_rejected(self):
        for extra in (
            {"dt_shell/authorization.py": b"pass"},
            {"dt_shell/__pycache__/authorization.cpython-312.pyc": b"bytecode"},
            {"dt_shell_release.c": b"generated code"},
        ):
            with self.subTest(extra=tuple(extra)), self.assertRaisesRegex(
                ValueError, "fallback|sources"
            ):
                release.seal(self.wheel(extra=extra), self.version, self.key)

    def test_wrong_version_and_public_key_are_rejected(self):
        path = self.wheel()
        with self.assertRaisesRegex(ValueError, "version"):
            release.seal(path, "0.0.0", self.key)
        with patch.dict(os.environ, {"DTS_RELEASE_PUBLIC_KEY": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "DTS_RELEASE_PUBLIC_KEY"):
                release.seal(path, self.version, self.key)

    def test_source_archives_and_universal_wheels_are_rejected(self):
        (self.directory / "duckietown-shell.tar.gz").write_bytes(b"source")
        with self.assertRaisesRegex(ValueError, "only release wheels"):
            release.verify_directory(self.directory, self.version, False)
        with self.assertRaisesRegex(ValueError, "native wheel"):
            release.wheel_coordinates(
                Path(f"duckietown_shell-{self.version}-py3-none-any.whl"), self.version
            )

    def test_missing_matrix_targets_block_publication(self):
        path = self.wheel(platform="manylinux_2_28_aarch64")
        release.seal(path, self.version, self.key)
        with self.assertRaisesRegex(ValueError, "Incomplete release matrix"):
            release.verify_directory(self.directory, self.version, True)

    def test_all_fifteen_targets_are_required_and_accepted(self):
        for python in ("cp310", "cp311", "cp312"):
            for platform in (
                "manylinux_2_28_x86_64",
                "manylinux_2_28_aarch64",
                "macosx_11_0_x86_64",
                "macosx_11_0_arm64",
                "win_amd64",
            ):
                path = self.wheel(python=python, platform=platform)
                release.seal(path, self.version, self.key)
        self.assertEqual(
            15, len(release.verify_directory(self.directory, self.version, True))
        )

    def test_release_build_cannot_omit_the_public_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DTS_RELEASE_PUBLIC_KEY"):
                release.release_public_key()

    def test_release_build_cannot_omit_the_command_public_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DTS_COMMANDS_PUBLIC_KEY"):
                release.commands_public_key()

    def test_wheel_with_the_wrong_command_trust_key_is_rejected(self):
        path = self.wheel()
        with patch.dict(os.environ, {"DTS_COMMANDS_PUBLIC_KEY": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "DTS_COMMANDS_PUBLIC_KEY"):
                release.seal(path, self.version, self.key)

    def test_release_requires_exact_approved_issuers_and_distinct_developer_keys(self):
        for keys in (
            {},
            {"https://hub.duckietown.com": "1" * 64},
            {**self.developer_keys, "https://untrusted.invalid": "3" * 64},
            {**self.developer_keys, "https://hub.duckietown.com": self.public},
            {**self.developer_keys, "https://hub.duckietown.com": self.commands_public},
            dict.fromkeys(self.developer_keys, "2" * 64),
            {**self.developer_keys, "https://hub.duckietown.com": "ABC"},
        ):
            with self.subTest(keys=keys), patch.dict(
                os.environ,
                {
                    "DTS_DEVELOPER_PUBLIC_KEYS": json.dumps(keys),
                },
            ), self.assertRaisesRegex(RuntimeError, "DTS_DEVELOPER_PUBLIC_KEYS"):
                release.developer_public_keys()
        with patch.dict(os.environ, {"DTS_DEVELOPER_PUBLIC_KEYS": ""}):
            with self.assertRaisesRegex(RuntimeError, "DTS_DEVELOPER_PUBLIC_KEYS"):
                release.developer_public_keys()

    def test_wheel_with_the_wrong_developer_trust_key_is_rejected(self):
        path = self.wheel()
        keys = {**self.developer_keys, "https://hub.duckietown.com": "0" * 64}
        with patch.dict(os.environ, {"DTS_DEVELOPER_PUBLIC_KEYS": json.dumps(keys)}):
            with self.assertRaisesRegex(ValueError, "DTS_DEVELOPER_PUBLIC_KEYS"):
                release.seal(path, self.version, self.key)

    def test_swapping_approved_issuer_keys_does_not_pass_wheel_validation(self):
        path = self.wheel()
        production = "https://hub.duckietown.com"
        staging = "https://staging-hub.duckietown.com"
        swapped = {
            production: self.developer_keys[staging],
            staging: self.developer_keys[production],
        }
        with patch.dict(os.environ, {"DTS_DEVELOPER_PUBLIC_KEYS": json.dumps(swapped)}):
            with self.assertRaisesRegex(ValueError, "DTS_DEVELOPER_PUBLIC_KEYS"):
                release.seal(path, self.version, self.key)

    def test_renderer_trust_is_mandatory_separate_and_exactly_mapped(self):
        wheel = self.wheel()
        with patch.dict(os.environ, {"DTM_RELEASE_PUBLIC_KEY": self.public}):
            with self.assertRaisesRegex(RuntimeError, "distinct"):
                release.renderer_release_public_key()
        with patch.dict(os.environ, {"DTM_RENDERER_PUBLIC_KEYS": ""}):
            with self.assertRaisesRegex(RuntimeError, "DTM_RENDERER_PUBLIC_KEYS"):
                release.renderer_public_keys()
        swapped = dict(zip(self.renderer_keys, reversed(list(self.renderer_keys.values()))))
        with patch.dict(os.environ, {"DTM_RENDERER_PUBLIC_KEYS": json.dumps(swapped)}):
            with self.assertRaisesRegex(ValueError, "DTM_RENDERER_PUBLIC_KEYS"):
                release.seal(wheel, self.version, self.key)

    def test_engine_trust_is_mandatory_distinct_and_embedded_exactly(self):
        wheel = self.wheel()
        with patch.dict(os.environ, {"DTM_ENGINE_RELEASE_PUBLIC_KEY": self.renderer_release_public}):
            with self.assertRaisesRegex(RuntimeError, "distinct"):
                release.engine_release_public_key()
        with patch.dict(os.environ, {"DTM_ENGINE_PUBLIC_KEYS": ""}):
            with self.assertRaisesRegex(RuntimeError, "DTM_ENGINE_PUBLIC_KEYS"):
                release.engine_public_keys()
        swapped = dict(zip(self.engine_keys, reversed(list(self.engine_keys.values()))))
        with patch.dict(os.environ, {"DTM_ENGINE_PUBLIC_KEYS": json.dumps(swapped)}):
            with self.assertRaisesRegex(ValueError, "DTM_ENGINE_PUBLIC_KEYS"):
                release.seal(wheel, self.version, self.key)


if __name__ == "__main__":
    unittest.main()
