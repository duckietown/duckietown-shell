import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from dt_shell_cli import dts as cli


class SourceCliTests(unittest.TestCase):
    def run_cli(self, code=None):
        env = dict(os.environ)
        for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
            env.pop(name, None)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = (
            [sys.executable, "-m", "dt_shell_cli.dts", "--help"]
            if code is None
            else [sys.executable, "-c", code, "--help"]
        )
        with tempfile.TemporaryDirectory() as directory:
            env["HOME"] = directory
            env["DTSHELL_ROOT"] = directory
            return subprocess.run(command, env=env, cwd=directory, capture_output=True, text=True, timeout=30)

    def test_source_startup_with_cython(self):
        result = self.run_cli()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_unrelated_module_entry_does_not_need_a_name(self):
        result = self.run_cli(
            "import sys; sys.modules['startup_probe'] = object(); " "from dt_shell_cli.dts import dts; dts()"
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_already_imported_shell_is_rejected(self):
        result = self.run_cli(
            "import sys; from types import ModuleType; "
            "sys.modules['dt_shell'] = ModuleType('dt_shell'); "
            "from dt_shell_cli.dts import dts; dts()"
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("The module 'dt_shell' was found imported", result.stderr)
        self.assertNotIn("usage:", result.stdout)

    def test_native_verification_precedes_the_import_guard(self):
        verify = Mock(side_effect=RuntimeError("native verification rejected"))
        with patch.object(cli.cython, "compiled", True), patch.dict(
            sys.modules,
            {
                "dt_shell": Mock(),
                "dt_shell_release": Mock(verify_installation=verify),
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "native verification rejected"):
                cli.dts()
        verify.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
