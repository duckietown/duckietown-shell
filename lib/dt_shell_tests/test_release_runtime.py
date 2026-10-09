import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SPEC = importlib.util.find_spec("dt_shell_release")


@unittest.skipUnless(SPEC is not None, "Requires an installed signed native release wheel")
class InstalledReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert SPEC is not None and SPEC.origin is not None
        cls.root = Path(SPEC.origin).resolve().parent
        cls.manifest = json.loads((cls.root / "duckietown_shell.integrity.json").read_bytes())

    def run_python(self, code, extra_env=None):
        env = dict(os.environ)
        for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
            env.pop(name, None)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=90
        )

    def assert_rejected(self, result, detail):
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Release integrity check failed:", result.stderr)
        self.assertIn(detail, result.stderr)

    def with_modified_file(
        self, relative, content, code="import dt_shell_release; dt_shell_release.launch()"
    ):
        path = self.root / relative
        original = path.read_bytes()
        try:
            path.write_bytes(content(original))
            return self.run_python(code)
        finally:
            path.write_bytes(original)

    def test_installed_core_is_native_and_valid(self):
        result = self.run_python(
            "import importlib.machinery, dt_shell_release; dt_shell_release.verify_installation(); "
            "from dt_shell.integrity import is_release_build; "
            "assert is_release_build(); "
            "import dt_shell.authorization, dt_shell.environments, dt_shell.commands.commands; "
            "assert all(m.__file__.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)) for m in "
            "(dt_shell.authorization, dt_shell.environments, dt_shell.commands.commands)); "
            "dt_shell_release.verify_installation()"
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_build_public_key_environment_is_not_a_runtime_override(self):
        result = self.run_python(
            "import dt_shell_release; dt_shell_release.verify_installation()",
            {"DTS_RELEASE_PUBLIC_KEY": "0" * 64},
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_release_rejects_source_overrides_even_if_empty(self):
        for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
            for value in ("", str(self.root)):
                with self.subTest(name=name, value=value):
                    result = self.run_python(
                        "import dt_shell_release; dt_shell_release.launch()", {name: value}
                    )
                    self.assertEqual(78, result.returncode)
                    self.assert_rejected(result, name)

    def test_modified_python_payload_is_rejected(self):
        result = self.with_modified_file("dt_shell/__init__.py", lambda value: value + b"\n# changed\n")
        self.assert_rejected(result, "'dt_shell/__init__.py' has been modified")

    def test_modified_native_payload_is_rejected(self):
        native = self.manifest["native_modules"]["dt_shell_cli.dts"]
        result = self.with_modified_file(native, lambda value: value + b"changed")
        self.assert_rejected(result, "has been modified")

    def test_missing_payload_is_rejected(self):
        path = self.root / "dt_shell/assets/requirements.txt"
        original = path.read_bytes()
        try:
            path.unlink()
            result = self.run_python("import dt_shell_release; dt_shell_release.launch()")
        finally:
            path.write_bytes(original)
        self.assert_rejected(result, "could not be read")

    def test_manifest_edits_and_wrong_key_signatures_are_rejected(self):
        result = self.with_modified_file("duckietown_shell.integrity.json", lambda value: value + b" ")
        self.assert_rejected(result, "signature is invalid")
        wrong = Ed25519PrivateKey.generate().sign(
            (self.root / "duckietown_shell.integrity.json").read_bytes()
        )
        result = self.with_modified_file("duckietown_shell.integrity.sig", lambda _: wrong)
        self.assert_rejected(result, "signature is invalid")

    def test_added_python_fallback_is_rejected(self):
        path = self.root / "dt_shell/authorization.py"
        self.assertFalse(path.exists())
        try:
            path.write_text("def require_ente_plan(*args): pass\n", encoding="ascii")
            result = self.run_python("import dt_shell_release; dt_shell_release.launch()")
        finally:
            path.unlink()
        self.assert_rejected(result, "unexpected file")

    def test_compiled_cli_and_delegated_entry_verify_independently(self):
        for code in (
            "from dt_shell_cli.dts import dts; dts()",
            "import dt_shell_release; dt_shell_release.delegated_main()",
            "from dt_shell_cli.main import main; main()",
        ):
            with self.subTest(code=code):
                result = self.with_modified_file(
                    "dt_shell/assets/requirements.txt", lambda value: value + b"\n# changed\n", code
                )
                self.assert_rejected(result, "has been modified")

    def test_exported_verifier_replacement_cannot_skip_bootstrap(self):
        result = self.with_modified_file(
            "dt_shell/assets/requirements.txt",
            lambda value: value + b"\n# changed\n",
            "import dt_shell_release; dt_shell_release.verify_installation = lambda: None; "
            "dt_shell_release.launch()",
        )
        self.assert_rejected(result, "has been modified")

    def test_dispatch_rechecks_integrity(self):
        result = self.run_python(
            "import dt_shell_release; dt_shell_release.verify_installation(); "
            "from pathlib import Path; from unittest.mock import Mock; "
            "from dt_shell.commands import DTCommandAbs; "
            "from dt_shell.constants import EMBEDDED_COMMAND_SET_NAME; "
            "path = Path(dt_shell_release.__file__).parent / 'dt_shell/assets/requirements.txt'; "
            "original = path.read_bytes(); "
            "descriptor = Mock(); descriptor.command.fake = False; "
            "descriptor.command_set.name = EMBEDDED_COMMAND_SET_NAME; "
            "class_code = 'class Probe(DTCommandAbs):\\n"
            " @classmethod\\n def get_command(cls, shell, line): return descriptor, []\\n'; "
            "exec(class_code)\n"
            "try:\n"
            " path.write_bytes(original + b'\\n# changed\\n'); Probe.do_command(Mock(), '')\n"
            "finally:\n"
            " path.write_bytes(original)\n"
        )
        self.assert_rejected(result, "has been modified")

    def test_real_console_entry_and_delegated_profile(self):
        with tempfile.TemporaryDirectory(prefix="dts-release-profile-") as temporary:
            home = Path(temporary)
            profile = home / "profiles" / "daffy"
            commands = profile / "commands" / "duckietown"
            commands.mkdir(parents=True)
            utilities = commands / "utils"
            utilities.mkdir()
            (utilities / "__init__.py").write_text("", encoding="ascii")
            (utilities / "table_utils.py").write_text(
                "def format_matrix(*args, **kwargs):\n"
                "    raise RuntimeError('Table formatting is outside the version fixture')\n",
                encoding="ascii",
            )
            subprocess.run(["git", "init", "-q", str(commands)], check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(commands),
                    "-c",
                    "user.name=DTS Test",
                    "-c",
                    "user.email=dts-test@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                    "--allow-empty",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(["git", "-C", str(commands), "tag", "v0.0.0"], check=True, capture_output=True)
            env = dict(os.environ)
            for name in (
                "DTSHELL_LIB",
                "DTSHELL_COMMANDS",
                "DTSHELL_PYTHONPATH",
                "DTSHELL_PROFILE",
                "DTSHELL_DISTRO",
                "DTSHELL_VENV_DIR",
                "IGNORE_ENVIRONMENTS",
            ):
                env.pop(name, None)
            env.update(
                HOME=temporary,
                USERPROFILE=temporary,
                DTSHELL_ROOT=str(home / "shell"),
                DTSHELL_DATABASES=str(home / "databases"),
                DTSHELL_PROFILES=str(home / "profiles"),
                DTHUB_URL="http://127.0.0.1:1",
                PYTHONUTF8="1",
            )
            setup = (
                "import time; from dt_shell.database import DTShellDatabase; "
                "from dt_shell.constants import DB_SETTINGS, DB_PROFILES, DB_UPDATES_CHECK; "
                "from dt_shell.profile import ShellProfile; "
                "from dt_shell.compatibility.migrations import mark_all_migrated; "
                "db = DTShellDatabase.open(DB_SETTINGS); "
                "db.update({'profile': 'daffy', 'check_for_updates': False, 'show_billboards': False}); "
                "p = ShellProfile('daffy', _distro='daffy'); "
                "p.secrets.dt1_token = 'fixture-only-no-real-token'; "
                "p.updates_check_db.set('upload_events', time.time()); "
                "DTShellDatabase.open(DB_UPDATES_CHECK).set('billboards', time.time()); "
                "from dt_shell.database.utils import InstalledDependenciesDatabase; "
                "from dt_shell.constants import SHELL_REQUIREMENTS_LIST; "
                "cache = InstalledDependenciesDatabase.load(p); "
                "cache.mark_as_installed(SHELL_REQUIREMENTS_LIST); "
                "[cache.mark_as_installed(cs.configuration.requirements()) for cs in p.command_sets "
                "if cs.configuration.requirements()]; "
                "mark_all_migrated()"
            )
            initialized = subprocess.run(
                [sys.executable, "-c", setup], env=env, capture_output=True, text=True, timeout=90
            )
            self.assertEqual(0, initialized.returncode, initialized.stdout + initialized.stderr)
            executable = Path(sys.executable).parent / ("dts.exe" if sys.platform == "win32" else "dts")
            env["DTSHELL_VENV_DIR"] = str(Path(sys.prefix))
            direct = subprocess.run(
                [str(executable), "version"], env=env, capture_output=True, text=True, timeout=90
            )
            self.assertEqual(0, direct.returncode, direct.stdout + direct.stderr)
            self.assertIn("shell: v" + self.manifest["version"], direct.stdout)
            env["IGNORE_ENVIRONMENTS"] = "1"
            delegated = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import dt_shell_release; dt_shell_release.delegated_main()",
                    "version",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(0, delegated.returncode, delegated.stdout + delegated.stderr)
            self.assertIn("shell: v" + self.manifest["version"], delegated.stdout)


if __name__ == "__main__":
    unittest.main()
