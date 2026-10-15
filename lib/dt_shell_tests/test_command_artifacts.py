import base64
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature

from dt_shell.commands import artifacts


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "command_release_tests", ROOT / "tools/commands_release.py"
)
assert SPEC is not None and SPEC.loader is not None
issuer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(issuer)


class CommandArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dts-command-artifacts-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.key = Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        environment = patch.dict(os.environ, {"DTS_COMMANDS_PUBLIC_KEY": public.hex()})
        environment.start()
        self.addCleanup(environment.stop)

        def verify_signature(signature, content):
            try:
                self.key.public_key().verify(signature, content)
            except InvalidSignature as error:
                raise ValueError("Invalid command signature") from error

        native = patch.dict(
            sys.modules,
            {
                "dt_shell_release": SimpleNamespace(
                    verify_command_signature=verify_signature
                ),
            },
        )
        native.start()
        self.addCleanup(native.stop)
        self.repository = "github.com/duckietown/duckietown-shell-commands"
        self.payload = issuer.fixture_payload()
        self.payload["__command_set__/requirements.txt"] = (b"requests>=2,<3\n", False)
        self.directory, self.manifest = self.bundle(1)
        self.store = artifacts.CommandArtifactStore(
            self.root / "cache", self.repository, "daffy", "daffy", "6.3.0"
        )

    def bundle(self, revision, distributions=None, payload=None, key=None):
        directory = self.root / f"bundle-{revision}-{len(list(self.root.iterdir()))}"
        manifest = issuer.build_payload(
            payload or self.payload,
            "a" * 40,
            self.repository,
            "daffy",
            distributions or ["daffy"],
            revision,
            ("0.0.0", "0.0.0", "999.999.999"),
            directory,
            key or self.key,
        )
        return directory, manifest

    def download(self, directory=None):
        directory = directory or self.directory

        def read(url, limit):
            return (directory / url.rsplit("/", 1)[-1]).read_bytes()

        return patch.object(artifacts, "_download", side_effect=read)

    def install(self):
        with self.download():
            return self.store.ensure(True)

    def signed_metadata(self, change):
        content, _ = artifacts.unpack_envelope(self.manifest.envelope)
        data = json.loads(content)
        change(data)
        content = artifacts.canonical_json(data)
        return artifacts.canonical_json(
            {
                "manifest": base64.b64encode(content).decode("ascii"),
                "signature": base64.b64encode(self.key.sign(content)).decode("ascii"),
            }
        )

    def test_real_signed_archive_has_complete_inventory(self):
        manifest = artifacts.verify_manifest(self.manifest.envelope)
        root, installed = self.install()
        self.assertEqual(manifest.identifier, installed.identifier)
        self.assertEqual(
            set(self.payload) | {artifacts.MANIFEST_NAME},
            {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()},
        )
        self.assertEqual("__command_set__/requirements.txt", manifest.requirements)
        self.assertEqual("a" * 40, manifest.commit)
        issuer.verify(self.directory)

    def test_unsigned_and_wrong_key_metadata_is_rejected(self):
        for value in (b"{}", b'{"manifest":"%%%","signature":"%%%"}'):
            with self.subTest(value=value), self.assertRaises(
                artifacts.CommandArtifactError
            ):
                artifacts.verify_manifest(value)
        _, foreign = self.bundle(2, key=Ed25519PrivateKey.generate())
        with self.assertRaisesRegex(
            artifacts.CommandArtifactError, "signature is invalid"
        ):
            artifacts.verify_manifest(foreign.envelope)

    def test_modified_envelope_is_rejected_even_with_valid_json(self):
        data = json.loads(self.manifest.envelope)
        content = base64.b64decode(data["manifest"])
        data["manifest"] = base64.b64encode(content + b" ").decode("ascii")
        with self.assertRaisesRegex(
            artifacts.CommandArtifactError, "signature is invalid"
        ):
            artifacts.verify_manifest(artifacts.canonical_json(data))

    def test_wrong_repository_channel_distribution_and_shell_are_rejected(self):
        manifest = artifacts.verify_manifest(self.manifest.envelope)
        for repository, branch, distro, version in (
            ("github.com/untrusted/commands", "daffy", "daffy", "6.3.0"),
            (self.repository, "ente", "daffy", "6.3.0"),
            (self.repository, "daffy", "ente", "6.3.0"),
            (self.repository, "daffy", "daffy", "1000.0.0"),
        ):
            with self.subTest(distro=distro, branch=branch), self.assertRaises(
                artifacts.CommandArtifactError
            ):
                manifest.matches(repository, branch, distro, version)

    def test_duplicate_fields_unsafe_files_and_invalid_dependency_metadata_are_rejected(
        self,
    ):
        for change in (
            lambda d: d["files"].update(
                {"../escape.py": next(iter(d["files"].values()))}
            ),
            lambda d: d["files"].update(
                {"utils/__pycache__/evil.pyc": next(iter(d["files"].values()))}
            ),
            lambda d: d["files"].update(
                {"Utils/__init__.py": d["files"]["utils/__init__.py"]}
            ),
            lambda d: d.update(requirements="../requirements.txt"),
            lambda d: d.update(revision=True),
            lambda d: d.update(format=True),
        ):
            with self.subTest(change=change), self.assertRaises(
                artifacts.CommandArtifactError
            ):
                artifacts.verify_manifest(self.signed_metadata(change))
        with self.assertRaisesRegex(artifacts.CommandArtifactError, "duplicate"):
            artifacts.unpack_envelope(b'{"manifest":"", "manifest":"", "signature":""}')

    def test_future_publication_is_rejected(self):
        envelope = self.signed_metadata(lambda d: d.update(created_at=9999999999))
        manifest = artifacts.verify_manifest(envelope)
        with self.assertRaisesRegex(
            artifacts.CommandArtifactError, "future publication"
        ):
            manifest.matches(self.repository, "daffy", "daffy", "6.3.0")

    def test_modified_hooks_configuration_utilities_and_dependencies_are_rejected_in_cache(
        self,
    ):
        root, _ = self.install()
        for relative in (
            "__command_set__/configuration.py",
            "__command_set__/init.py",
            "utils/__init__.py",
            "probe/command.py",
            "__command_set__/requirements.txt",
        ):
            file = root / relative
            original = file.read_bytes()
            try:
                file.write_bytes(original + b"\n# modified\n")
                with self.subTest(relative=relative), self.assertRaisesRegex(
                    artifacts.CommandArtifactError, "modified"
                ):
                    self.store.cached()
            finally:
                file.write_bytes(original)

    def test_added_missing_and_cached_bytecode_files_are_rejected(self):
        root, _ = self.install()
        for relative in (
            "utils/extra.py",
            "utils/__pycache__/extra.cpython-312.pyc",
            "extra.dll",
        ):
            file = root / relative
            file.parent.mkdir(exist_ok=True)
            try:
                file.write_bytes(b"untrusted")
                with self.subTest(relative=relative), self.assertRaisesRegex(
                    artifacts.CommandArtifactError, "unexpected"
                ):
                    self.store.cached()
            finally:
                file.unlink()
        file = root / "__command_set__/init.py"
        original = file.read_bytes()
        try:
            file.unlink()
            with self.assertRaisesRegex(artifacts.CommandArtifactError, "missing"):
                self.store.cached()
        finally:
            file.write_bytes(original)

    @unittest.skipIf(
        sys.platform == "win32", "Creating symlinks may require Windows elevation"
    )
    def test_symlinks_are_rejected(self):
        root, _ = self.install()
        path = root / "link"
        path.symlink_to(root / "probe", target_is_directory=True)
        with self.assertRaisesRegex(artifacts.CommandArtifactError, "symbolic links"):
            self.store.cached()

    def test_tampered_cache_is_not_silently_replaced_with_a_download(self):
        root, _ = self.install()
        (root / "probe/command.py").write_bytes(b"tampered")
        with self.download() as download, self.assertRaises(
            artifacts.CommandArtifactError
        ):
            self.store.ensure(True)
        download.assert_not_called()

    def test_verified_offline_cache_warns_but_first_install_fails(self):
        root, _ = self.install()
        warnings = []
        with patch.object(
            artifacts,
            "_download",
            side_effect=artifacts.CommandArtifactUnavailable("offline"),
        ):
            self.assertEqual(root, self.store.ensure(True, warn=warnings.append)[0])
            self.assertIn("verified cached", warnings[0])
            fresh = artifacts.CommandArtifactStore(
                self.root / "fresh", self.repository, "daffy", "daffy", "6.3.0"
            )
            with self.assertRaisesRegex(
                artifacts.CommandArtifactUnavailable, "offline"
            ):
                fresh.ensure(True, warn=warnings.append)
            with self.assertRaises(artifacts.CommandArtifactUnavailable):
                self.store.ensure(True)

    def test_readonly_load_never_downloads_or_modifies_cache(self):
        root, _ = self.install()
        with patch.object(artifacts, "_download") as download:
            self.assertEqual(root, self.store.ensure(True, readonly=True)[0])
            download.assert_not_called()
        fresh = artifacts.CommandArtifactStore(
            self.root / "readonly", self.repository, "daffy", "daffy", "6.3.0"
        )
        with self.assertRaisesRegex(
            artifacts.CommandArtifactError, "no verified cache"
        ):
            fresh.ensure(True, readonly=True)
        self.assertFalse(fresh.cache.exists())

    def test_updates_use_new_generations_and_reject_rollbacks_and_revision_reuse(self):
        old_root, old = self.install()
        changed = dict(self.payload)
        changed["utils/new.py"] = (b"UPDATED = True\n", False)
        directory, new = self.bundle(2, payload=changed)
        with self.download(directory):
            new_root, installed = self.store.ensure(True)
        self.assertEqual(new.identifier, installed.identifier)
        self.assertNotEqual(old_root, new_root)
        artifacts.verify_snapshot(old_root, old)
        with self.download(), self.assertRaisesRegex(
            artifacts.CommandArtifactError, "stale"
        ):
            self.store.ensure(True)
        directory, _ = self.bundle(2)
        with self.download(directory), self.assertRaisesRegex(
            artifacts.CommandArtifactError, "reused"
        ):
            self.store.ensure(True)
        self.assertEqual(new_root, self.store.cached()[0])

    def test_failed_update_preserves_the_previous_verified_snapshot(self):
        old_root, _ = self.install()
        directory, new = self.bundle(2)
        (directory / new.archive_name).write_bytes(b"modified zip")
        with self.download(directory), self.assertRaises(
            artifacts.CommandArtifactError
        ):
            self.store.ensure(True)
        self.assertEqual(old_root, self.store.cached()[0])
        self.assertFalse(any(self.store.store.glob(".staging-*")))

    def test_invalid_initial_archive_does_not_poison_the_cache(self):
        directory, manifest = self.bundle(2)
        (directory / manifest.archive_name).write_bytes(b"invalid archive")
        with self.download(directory), self.assertRaises(
            artifacts.CommandArtifactError
        ):
            self.store.ensure(True)
        self.assertIsNone(self.store.cached())
        self.assertFalse(list(self.store.cache.glob(".staging-*")))
        self.install()

    @unittest.skipIf(
        os.name == "nt", "Windows does not preserve POSIX executable modes"
    )
    def test_modified_executable_permissions_are_rejected(self):
        root, _ = self.install()
        (root / "probe/command.py").chmod(0o755)
        with self.assertRaisesRegex(
            artifacts.CommandArtifactError, "executable permissions"
        ):
            self.store.cached()

    def test_legacy_git_cache_is_migrated_without_executing_or_deleting_it(self):
        self.store.cache.mkdir()
        unsigned = self.store.cache / "__command_set__"
        unsigned.mkdir()
        marker = self.root / "unsigned-executed"
        (unsigned / "configuration.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        )
        root, _ = self.install()
        self.assertFalse(marker.exists())
        self.assertTrue((unsigned / "configuration.py").exists())
        self.assertNotEqual(self.store.cache, root)

    def test_import_loader_uses_verified_source_without_creating_bytecode(self):
        root, manifest = self.install()
        path = root / "probe/command.py"
        loader = artifacts.VerifiedSourceLoader(
            "signed_probe", str(path), root, manifest
        )
        self.assertIsNotNone(loader.get_code("signed_probe"))
        self.assertFalse(list(root.rglob("*.pyc")))
        path.write_bytes(b"raise RuntimeError('UNTRUSTED_EXECUTED')\n")
        with self.assertRaisesRegex(artifacts.CommandArtifactError, "modified"):
            loader.get_code("signed_probe")

    def test_valid_poisoned_bytecode_is_never_executed_by_the_verified_loader(self):
        root, manifest = self.install()
        source = root / "probe/command.py"
        status = source.stat()
        poisoned = compile(
            "raise RuntimeError('POISONED_CACHE_EXECUTED')", str(source), "exec"
        )
        cache = Path(importlib.util.cache_from_source(str(source)))
        cache.parent.mkdir()
        cache.write_bytes(
            importlib.util.MAGIC_NUMBER
            + struct.pack("<III", 0, int(status.st_mtime), status.st_size)
            + marshal.dumps(poisoned)
        )
        ordinary = importlib.machinery.SourceFileLoader("ordinary_probe", str(source))
        with self.assertRaisesRegex(RuntimeError, "POISONED_CACHE_EXECUTED"):
            exec(ordinary.get_code("ordinary_probe"), {})
        loader = artifacts.VerifiedSourceLoader(
            "signed_probe", str(source), root, manifest
        )
        namespace = {"__name__": "signed_probe"}
        exec(loader.get_code("signed_probe"), namespace)
        self.assertIn("DTCommand", namespace)
        with self.assertRaisesRegex(artifacts.CommandArtifactError, "unexpected"):
            self.store.cached()

    def test_nested_dependencies_are_signed_and_external_includes_are_rejected(self):
        payload = dict(self.payload)
        payload["__command_set__/requirements.txt"] = (b"-r nested.txt\n", False)
        payload["__command_set__/nested.txt"] = (
            b"-c constraints.txt\nrequests\n",
            False,
        )
        payload["__command_set__/constraints.txt"] = (b"requests==2.32.5\n", False)
        directory, manifest = self.bundle(2, payload=payload)
        root = self.root / "dependency-snapshot"
        root.mkdir()
        artifacts.extract_archive(
            (directory / manifest.archive_name).read_bytes(), root, manifest
        )
        (root / "__command_set__/constraints.txt").write_bytes(b"modified")
        with self.assertRaisesRegex(artifacts.CommandArtifactError, "modified"):
            artifacts.verify_requirements(root, manifest)
        payload["__command_set__/requirements.txt"] = (b"-r ../../outside.txt\n", False)
        with self.assertRaisesRegex(RuntimeError, "outside the signed"):
            self.bundle(3, payload=payload)

    def test_tracked_packaging_does_not_import_configuration(self):
        source = self.root / "checkout"
        source.mkdir()
        marker = self.root / "configuration-executed"
        config = source / "__command_set__"
        config.mkdir()
        text = issuer.fixture_payload()["__command_set__/configuration.py"][0].decode()
        (config / "configuration.py").write_text(
            text + f"\nraise RuntimeError({str(marker)!r})\n"
        )
        subprocess.run(
            ["git", "init", "-q", str(source)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(source), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "user.name=DTS Test",
                "-c",
                "user.email=dts@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
            capture_output=True,
        )
        directory = self.root / "tracked-release"
        built = issuer.build(
            source, directory, self.repository, "daffy", ["daffy"], 3, self.key
        )
        self.assertEqual("0.0.0", built.version)
        self.assertFalse(marker.exists())
        (config / "configuration.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "clean"):
            issuer.build(
                source,
                self.root / "dirty-release",
                self.repository,
                "daffy",
                ["daffy"],
                4,
                self.key,
            )

    def test_release_readiness_requires_all_four_correctly_signed_compatible_channels(
        self,
    ):
        responses = {}
        for branch in ("ente", "ente-staging", "daffy", "daffy-staging"):
            directory = self.root / ("ready-" + branch)
            manifest = issuer.build_payload(
                self.payload,
                "a" * 40,
                self.repository,
                branch,
                [branch.split("-")[0]],
                1,
                ("0.0.0", "0.0.0", "999.999.999"),
                directory,
                self.key,
            )
            responses[
                issuer.artifacts.artifact_url(
                    self.repository, branch, issuer.artifacts.MANIFEST_NAME
                )
            ] = manifest.envelope
            responses[
                issuer.artifacts.artifact_url(
                    self.repository, branch, manifest.archive_name
                )
            ] = (directory / manifest.archive_name).read_bytes()

        def fetch(url, limit):
            if url not in responses:
                raise issuer.artifacts.CommandArtifactUnavailable("Missing channel")
            return responses[url]

        with patch.object(issuer.artifacts, "_download", side_effect=fetch) as download:
            issuer.ready(self.repository, "6.3.0")
            self.assertEqual(8, download.call_count)
            del responses[
                issuer.artifacts.artifact_url(
                    self.repository, "daffy-staging", issuer.artifacts.MANIFEST_NAME
                )
            ]
            with self.assertRaisesRegex(RuntimeError, "Missing channel"):
                issuer.ready(self.repository, "6.3.0")


if __name__ == "__main__":
    unittest.main()
