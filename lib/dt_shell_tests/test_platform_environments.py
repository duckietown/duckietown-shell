import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from dt_shell.checks.environment import check_user_in_docker_group, running_with_sudo
from dt_shell.environments import (
    VirtualPython3Environment,
    check_release_interpreter,
    virtualenv_interpreter,
)
from dt_shell.exceptions import ShellInitException, UserError


class PlatformEnvironmentTests(unittest.TestCase):
    def test_windows_does_not_require_unix_privilege_or_group_apis(self):
        with patch("dt_shell.checks.environment.sys.platform", "win32"):
            self.assertFalse(running_with_sudo())
            check_user_in_docker_group()

    def test_venv_interpreters_use_platform_paths(self):
        for platform, directory, executable in (
            ("linux", "bin", "python3"),
            ("darwin", "bin", "python3"),
            ("win32", "Scripts", "python.exe"),
        ):
            with self.subTest(platform=platform), patch("dt_shell.environments.sys.platform", platform):
                self.assertEqual(
                    os.path.join("profile", directory, executable), virtualenv_interpreter("profile")
                )

    def test_native_release_rejects_incompatible_profile_abis(self):
        actual = json.dumps(["cpython-999", "linux", "aarch64"])
        with patch("dt_shell.environments.is_release_build", return_value=True), patch(
            "dt_shell.environments.subprocess.check_output", return_value=actual
        ):
            with self.assertRaisesRegex(UserError, "incompatible with this compiled DTS"):
                check_release_interpreter("profile-python")

    def test_interpreter_probe_errors_are_explicit(self):
        for error in (
            OSError("missing"),
            subprocess.CalledProcessError(1, "python"),
            subprocess.TimeoutExpired("python", 10),
        ):
            with self.subTest(error=type(error)), patch(
                "dt_shell.environments.is_release_build", return_value=True
            ), patch("dt_shell.environments.subprocess.check_output", side_effect=error):
                with self.assertRaisesRegex(ShellInitException, "Could not check the profile interpreter"):
                    check_release_interpreter("profile-python")

    def test_source_development_does_not_impose_a_native_abi(self):
        with patch("dt_shell.environments.is_release_build", return_value=False), patch(
            "dt_shell.environments.subprocess.check_output"
        ) as execute:
            check_release_interpreter("source-python")
            execute.assert_not_called()

    def test_windows_delegation_uses_import_entry_and_path_separator(self):
        with tempfile.TemporaryDirectory() as directory:
            interpreter = Path(directory) / "Scripts" / "python.exe"
            interpreter.parent.mkdir()
            interpreter.touch()
            shell = Mock(command_sets=[])
            cache = Mock()
            cache.needs_install_step.return_value = False
            with patch.dict(os.environ, {"DTSHELL_VENV_DIR": directory}), patch(
                "dt_shell.environments.sys.platform", "win32"
            ), patch("dt_shell.environments.os.pathsep", ";"), patch(
                "dt_shell.environments.sys.path", ["C:\\dts", "C:\\commands"]
            ), patch(
                "dt_shell.environments.sys.argv", ["dts", "version"]
            ), patch(
                "dt_shell.environments.is_release_build", return_value=False
            ), patch(
                "dt_shell.environments.verify_release_integrity"
            ), patch(
                "dt_shell.environments.InstalledDependenciesDatabase.load", return_value=cache
            ), patch(
                "dt_shell.environments.os.execle"
            ) as execute:
                VirtualPython3Environment().execute(shell, [])
            arguments = execute.call_args.args
            self.assertEqual(str(interpreter), arguments[0])
            self.assertEqual("-c", arguments[2])
            self.assertIn("from dt_shell_cli.main import main", arguments[3])
            self.assertEqual("C:\\dts;C:\\commands", arguments[-1]["EXTRA_PYTHONPATH"])
            self.assertNotIn("PYTHONPATH", arguments[-1])


if __name__ == "__main__":
    unittest.main()
