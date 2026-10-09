import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_tools", ROOT / "tools/release.py")
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
        environment = patch.dict(os.environ, {"DTS_RELEASE_PUBLIC_KEY": self.public})
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
            info + "/WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n".encode("ascii"),
            info + "/entry_points.txt": b"[console_scripts]\ndts = dt_shell_release:launch\n",
            info + "/RECORD": b"",
            "dt_shell/__init__.py": b"",
            "dt_shell_cli/__init__.py": b"",
            "dt_shell/assets/requirements.txt": b"cryptography\n",
            "dt_shell/embedded/command_descriptions.yaml": b"version: {}\n",
        }
        suffix = ".pyd" if platform.startswith("win_") else ".so"
        for module in (*release.PROTECTED_MODULES, "dt_shell_release"):
            data[module.replace(".", "/") + "." + python + suffix] = (module + self.public).encode("ascii")
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
            self.assertFalse(any(private in archive.read(name) for name in archive.namelist()))

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
            with self.subTest(extra=tuple(extra)), self.assertRaisesRegex(ValueError, "fallback|sources"):
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
            release.wheel_coordinates(Path(f"duckietown_shell-{self.version}-py3-none-any.whl"), self.version)

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
        self.assertEqual(15, len(release.verify_directory(self.directory, self.version, True)))

    def test_release_build_cannot_omit_the_public_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DTS_RELEASE_PUBLIC_KEY"):
                release.release_public_key()


if __name__ == "__main__":
    unittest.main()
