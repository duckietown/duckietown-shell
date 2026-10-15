import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from dt_shell.integrity import is_release_build


@unittest.skipUnless(
    is_release_build(), "Requires an installed signed native DTS wheel"
)
class InstalledCommandArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = os.environ.get("DTS_COMMANDS_TEST_BUNDLE")
        if not bundle:
            raise RuntimeError(
                "Set DTS_COMMANDS_TEST_BUNDLE to a fixture signed by the embedded command key."
            )
        cls.bundle = Path(bundle).resolve()

    def run_python(self, body, extra=None):
        environment = dict(os.environ)
        for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
            environment.pop(name, None)
        environment.update(extra or {})
        return subprocess.run(
            [sys.executable, "-c", body],
            capture_output=True,
            text=True,
            env=environment,
            timeout=90,
        )

    def script(self, cache, body):
        return (
            "import time, sys; from pathlib import Path; from types import SimpleNamespace; "
            "from dt_shell.commands import CommandSet; from dt_shell.commands.repository import CommandsRepository; "
            "from dt_shell.commands import artifacts; from unittest.mock import Mock, patch; "
            f"bundle = Path({str(self.bundle)!r}); cache = Path({str(cache)!r}); "
            "manifest = artifacts.verify_manifest((bundle / artifacts.MANIFEST_NAME).read_bytes()); "
            "store = cache / artifacts.STORE_NAME; store.mkdir(parents=True); "
            "root = store / manifest.identifier; root.mkdir(); "
            "artifacts.extract_archive((bundle / manifest.archive_name).read_bytes(), root, manifest); "
            "(store / artifacts.INDEX_NAME).write_bytes(manifest.envelope); "
            "db = Mock(); db.get.return_value = {'time': time.time()}; "
            "profile = SimpleNamespace(readonly=False, distro=SimpleNamespace(name='daffy', branch='daffy'), "
            "database=lambda name: db); "
            "repository = CommandsRepository('duckietown', 'duckietown-shell-commands', 'daffy')\n"
            + body
        )

    def assert_blocked(self, body, expected):
        with tempfile.TemporaryDirectory(prefix="dts-native-command-") as temporary:
            result = self.run_python(self.script(Path(temporary) / "cache", body))
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout + result.stderr)
        self.assertNotIn("UNTRUSTED_EXECUTED", result.stdout)

    def test_native_verifier_key_cannot_be_selected_using_environment_variables(self):
        result = self.run_python(
            "from pathlib import Path; from dt_shell.commands import artifacts; "
            f"artifacts.verify_manifest(Path({str(self.bundle / 'duckietown_commands.json')!r}).read_bytes())",
            {"DTS_COMMANDS_PUBLIC_KEY": "0" * 64, "DTHUB_HOST": "untrusted.invalid"},
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_unsigned_wrong_key_and_wrong_distribution_are_rejected_before_import(self):
        self.assert_blocked(
            "(store / artifacts.INDEX_NAME).write_bytes(b'{}'); "
            "CommandSet('duckietown', str(cache), profile, repository)",
            "unsupported signed envelope",
        )
        self.assert_blocked(
            "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; "
            "import base64; content, signature = artifacts.unpack_envelope(manifest.envelope); "
            "(store / artifacts.INDEX_NAME).write_bytes(artifacts.canonical_json({"
            "'manifest': base64.b64encode(content).decode(), "
            "'signature': base64.b64encode(Ed25519PrivateKey.generate().sign(content)).decode()})); "
            "CommandSet('duckietown', str(cache), profile, repository)",
            "signature is invalid",
        )
        self.assert_blocked(
            "repository.branch = 'ente'; CommandSet('duckietown', str(cache), profile, repository)",
            "different repository or release channel",
        )
        self.assert_blocked(
            "profile.distro.name = 'ente'; CommandSet('duckietown', str(cache), profile, repository)",
            "not approved for the 'ente' distribution",
        )

    def test_each_executable_surface_is_checked_before_configuration(self):
        for relative in (
            "__command_set__/configuration.py",
            "__command_set__/init.py",
            "utils/__init__.py",
            "probe/__init__.py",
            "probe/command.py",
        ):
            with self.subTest(relative=relative):
                self.assert_blocked(
                    f"(root / {relative!r}).write_text(\"print('UNTRUSTED_EXECUTED')\\n\"); "
                    "CommandSet('duckietown', str(cache), profile, repository)",
                    "modified",
                )

    def test_added_files_and_bytecode_are_rejected_before_any_hook(self):
        for relative in ("utils/extra.py", "utils/__pycache__/extra.pyc"):
            with self.subTest(relative=relative):
                self.assert_blocked(
                    f"p = root / {relative!r}; p.parent.mkdir(exist_ok=True); p.write_bytes(b'untrusted'); "
                    "CommandSet('duckietown', str(cache), profile, repository)",
                    "unexpected",
                )

    def test_native_command_configuration_initialization_and_execution_use_signed_source(
        self,
    ):
        with tempfile.TemporaryDirectory(prefix="dts-native-command-") as temporary:
            result = self.run_python(
                self.script(
                    Path(temporary) / "cache",
                    "cs = CommandSet('duckietown', str(cache), profile, repository); cs.init(); "
                    "assert cs.version == manifest.version and cs.local_sha == manifest.commit; "
                    "sys.path.insert(0, cs.path); from dt_shell.commands.importer import import_command; "
                    "command = import_command(cs, str(root / 'probe')); command.command(None, []); "
                    "assert not list(root.rglob('*.pyc'))",
                )
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SIGNED_COMMAND_EXECUTED", result.stdout)

    def test_loading_a_cached_snapshot_does_not_postpone_automatic_update_checks(self):
        with tempfile.TemporaryDirectory(
            prefix="dts-native-command-check-"
        ) as temporary:
            result = self.run_python(
                self.script(
                    Path(temporary) / "cache",
                    "last_checked = time.time() - 60; db.get.return_value = {'time': last_checked}; "
                    "CommandSet('duckietown', str(cache), profile, repository); "
                    "assert db.set.call_args.args[1]['time'] == last_checked",
                )
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_import_and_dependency_checks_cannot_use_a_tampered_cached_snapshot(self):
        self.assert_blocked(
            "cs = CommandSet('duckietown', str(cache), profile, repository); "
            "(root / 'utils/__init__.py').write_text(\"print('UNTRUSTED_EXECUTED')\\n\"); "
            "cs.requirements()",
            "modified",
        )
        self.assert_blocked(
            "cs = CommandSet('duckietown', str(cache), profile, repository); "
            "(root / 'probe/command.py').write_text(\"print('UNTRUSTED_EXECUTED')\\n\"); "
            "from dt_shell.commands.importer import import_command; import_command(cs, str(root / 'probe'))",
            "modified",
        )

    def test_dispatch_rechecks_external_command_content(self):
        self.assert_blocked(
            "cs = CommandSet('duckietown', str(cache), profile, repository); "
            "from dt_shell.commands import DTCommandAbs; "
            "descriptor = Mock(); descriptor.command.fake = False; descriptor.command_set = cs; "
            "descriptor.path = str(root / 'probe'); "
            "exec('class Probe(DTCommandAbs):\\n"
            " @classmethod\\n def get_command(cls, shell, line): return descriptor, []\\n'); "
            "(root / 'probe/command.py').write_text(\"print('UNTRUSTED_EXECUTED')\\n\"); "
            "Probe.do_command(Mock(), '')",
            "modified",
        )

    def test_empty_cache_requires_artifact_download_not_git_clone(self):
        self.assert_blocked(
            "import shutil; shutil.rmtree(store)\n"
            "with patch('dt_shell.commands.artifacts._download', "
            "side_effect=artifacts.CommandArtifactUnavailable('signed release unavailable')):\n"
            " CommandSet('duckietown', str(cache), profile, repository)",
            "signed release unavailable",
        )

    def test_native_update_changes_generation_and_invalidates_old_modules_and_commands(
        self,
    ):
        with tempfile.TemporaryDirectory(
            prefix="dts-native-command-update-"
        ) as temporary:
            result = self.run_python(
                self.script(
                    Path(temporary) / "cache",
                    "cs = CommandSet('duckietown', str(cache), profile, repository); "
                    "sys.path.insert(0, cs.path); import utils; assert utils.FIXTURE_GENERATION == 1; "
                    "from dt_shell.commands.importer import import_command; "
                    "old = import_command(cs, str(root / 'probe')); "
                    "next_envelope = artifacts.verified_file(root, '__fixture_update__/next-envelope.json', manifest); "
                    "next_manifest = artifacts.verify_manifest(next_envelope); "
                    "next_archive = artifacts.verified_file(root, '__fixture_update__/' + next_manifest.archive_name, "
                    "manifest); "
                    "def_code = 'def fetch(url, limit):\\n"
                    " return next_envelope if url.endswith(artifacts.MANIFEST_NAME) else next_archive\\n'; "
                    "exec(def_code)\n"
                    "with patch.object(artifacts, '_download', side_effect=fetch):\n"
                    " assert cs.update(force=True)\n"
                    "assert Path(cs.path) != root; import utils; assert utils.FIXTURE_GENERATION == 2; "
                    "new = import_command(cs, str(Path(cs.path) / 'probe')); assert new is not old; "
                    "new.command(None, [])\n"
                    "try:\n"
                    " cs.verify_integrity(str(root / 'probe'))\n"
                    "except Exception as error:\n"
                    " assert 'Restart DTS' in str(error)\n"
                    "else:\n"
                    " raise AssertionError('Old generation was accepted')\n",
                )
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("UPDATED_SIGNED_COMMAND_EXECUTED", result.stdout)

    def test_source_override_is_not_enabled_by_signed_plan_or_staff_status(self):
        result = self.run_python(
            "import dt_shell_release; dt_shell_release.launch()",
            {"DTSHELL_COMMANDS": str(self.bundle), "DTS_DEVELOPER_MODE": "1"},
        )
        self.assertEqual(78, result.returncode, result.stderr)
        self.assertIn("DTSHELL_COMMANDS", result.stderr)


if __name__ == "__main__":
    unittest.main()
