from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from dt_shell import DTShell
from dt_shell.checks.environment import check_user_in_docker_group, running_with_sudo
from dt_shell.commands import CommandSet
from dt_shell.constants import (
    DB_INSTALLED_DEPENDENCIES,
    DTShellConstants,
    EMBEDDED_COMMAND_SET_NAME,
    SHELL_LIB_DIR,
    SHELL_REQUIREMENTS_LIST,
)
from dt_shell.database import DTShellDatabase
from dt_shell.database.utils import InstalledDependenciesDatabase
from dt_shell.embedded.profile.dependencies.reinstall import command as reinstall
from dt_shell.environments import (
    Python3Environment,
    VirtualPython3Environment,
    check_release_interpreter,
    virtualenv_interpreter,
)
from dt_shell.exceptions import CommandNotFound, CommandsLoadingException, ShellInitException, UserError
from dt_shell.profile import ShellProfile


class DependencyCacheTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        registry = patch.object(DTShellDatabase, "_instances", {})
        registry.start()
        self.addCleanup(registry.stop)
        self.requirements = self.root / "requirements.txt"
        self.requirements.write_text("example-package==1\n")
        self.legacy = InstalledDependenciesDatabase.open(
            DB_INSTALLED_DEPENDENCIES, location=str(self.root / "profile" / "databases")
        )
        self.legacy.mark_as_installed(SHELL_REQUIREMENTS_LIST)
        self.legacy.mark_as_installed(str(self.requirements))
        self.profile = Mock(path=str(self.root / "profile"))
        self.profile.database.return_value = self.legacy
        command_set = Mock()
        command_set.name = "development"
        command_set.requirements.return_value = str(self.requirements)
        self.shell = Mock(profile=self.profile, command_sets=[command_set])

    def run_environment(self, environment):
        interpreter = Path(virtualenv_interpreter(str(environment)))
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        interpreter.touch()
        # A new DTS process does not retain database instances from the previous invocation.
        DTShellDatabase._instances.clear()
        with patch.dict(os.environ, {"DTSHELL_VENV_DIR": str(environment)}), patch(
            "dt_shell.environments.check_release_interpreter"
        ), patch("dt_shell.environments.verify_release_integrity"), patch(
            "dt_shell.environments.is_release_build", return_value=False
        ), patch(
            "dt_shell.environments.is_developer_mode", return_value=False
        ), patch(
            "dt_shell.environments.pip_install"
        ) as install, patch(
            "dt_shell.environments.os.execle"
        ) as execute:
            VirtualPython3Environment().execute(self.shell, [])
        execute.assert_called_once()
        return install

    def expected_installs(self, environment):
        interpreter = virtualenv_interpreter(str(environment))
        return [
            call(interpreter, SHELL_REQUIREMENTS_LIST),
            call(interpreter, str(self.requirements)),
        ]

    def test_legacy_profile_cache_does_not_skip_new_environment_dependencies(self):
        environment = self.root / "environment"
        original = Path(self.legacy.yaml).read_bytes()
        install = self.run_environment(environment)
        self.assertEqual(self.expected_installs(environment), install.call_args_list)
        self.assertEqual(original, Path(self.legacy.yaml).read_bytes())

    def test_unchanged_environment_reuses_its_dependency_cache(self):
        environment = self.root / "environment"
        first = self.run_environment(environment)
        self.assertEqual(self.expected_installs(environment), first.call_args_list)
        self.run_environment(environment).assert_not_called()

    def test_switching_environments_does_not_share_installation_records(self):
        first, second = self.root / "first", self.root / "second"
        self.assertEqual(self.expected_installs(first), self.run_environment(first).call_args_list)
        self.assertEqual(self.expected_installs(second), self.run_environment(second).call_args_list)
        self.run_environment(first).assert_not_called()

    def test_recreated_environment_at_same_path_reinstalls_dependencies(self):
        environment = self.root / "environment"
        self.run_environment(environment)
        environment.rename(self.root / "previous-environment")
        install = self.run_environment(environment)
        self.assertEqual(self.expected_installs(environment), install.call_args_list)

    def test_changed_requirements_reinstall_only_the_changed_manifest(self):
        environment = self.root / "environment"
        self.run_environment(environment)
        self.requirements.write_text("example-package==2\n")
        install = self.run_environment(environment)
        self.assertEqual(
            [call(virtualenv_interpreter(str(environment)), str(self.requirements))], install.call_args_list
        )

    def test_reinstall_records_dependencies_in_the_running_environment(self):
        shell = Mock(command_sets=[])
        with patch.object(reinstall, "pip_install"), patch.object(
            reinstall.InstalledDependenciesDatabase, "load"
        ) as load:
            reinstall.DTCommand.command(shell, [])
        load.assert_called_once_with(sys.prefix)


class PythonEnvironmentDispatchTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        embedded = str(Path(SHELL_LIB_DIR) / "embedded")
        stack.enter_context(patch("sys.path", [embedded, *sys.path]))
        stack.enter_context(patch.dict("sys.modules"))
        stack.enter_context(patch.object(DTShell, "include", SimpleNamespace(), create=True))
        stack.enter_context(patch("dt_shell.environments.print_debug_info"))
        for name in ("developer", "exit", "quit"):
            for prefix in ("do_", "get_", "complete_", "help_"):
                stack.enter_context(patch.object(DTShell, prefix + name, create=True))
        profile = Mock(command_descriptions={})
        ShellProfile.update_command_descriptions(profile, embedded)
        commands = CommandSet(EMBEDDED_COMMAND_SET_NAME, embedded, profile, leave_alone=True)
        commands.commands = {name: commands.commands[name] for name in ("developer", "exit")}
        profile.command_sets = [commands]
        self.shell = DTShell.__new__(DTShell)
        self.shell._profile = profile
        self.shell._skeleton = True
        self.shell._errors_loading = []
        self.shell.load_commands(skeleton=True)

    def execute(self, args, expected_code):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors), self.assertRaises(SystemExit) as result:
            Python3Environment().execute(self.shell, args)
        self.assertEqual(expected_code, result.exception.code)
        return output.getvalue(), errors.getvalue()

    def test_developer_is_a_group_of_discoverable_leaf_commands(self):
        commands = self.shell.commands["developer"]
        self.assertIsInstance(commands, dict)
        self.assertEqual({"status", "renew", "clear"}, set(commands))
        descriptions = self.shell.profile.command_descriptions["developer"]["subcommands"]
        self.assertEqual(set(commands), set(descriptions))
        for subcommand in commands:
            with self.subTest(subcommand=subcommand):
                descriptor = self.shell.get_command(f"developer {subcommand}")
                self.assertEqual(f"developer.{subcommand}", descriptor.selector)
                self.assertTrue(descriptor.command.fake)
                self.assertIsInstance(descriptor.environment, Python3Environment)
                self.assertTrue(descriptions[subcommand]["description"])
        with self.assertRaises(CommandNotFound):
            self.shell.get_command("developer")
        with self.assertRaises(CommandNotFound):
            self.shell.get_command("developer unknown")

    def test_developer_completion_suggests_subcommands_and_filters_prefixes(self):
        self.assertTrue(
            {"status", "renew", "clear"}.issubset(self.shell.complete_developer("", "developer ", 10, 10))
        )
        self.assertEqual(["status"], self.shell.complete_developer("st", "developer st", 10, 12))

    def test_cli_lists_described_subcommands_for_group_help_and_rejects_unknown_names(self):
        from dt_shell_cli import dts as entrypoint

        for arguments, expected_code in (
            (["developer"], None),
            (["developer", "--help"], None),
            (["developer", "-h"], None),
            (["developer", "unknown"], 2),
        ):
            with self.subTest(arguments=arguments), ExitStack() as stack:
                output = stack.enter_context(redirect_stdout(io.StringIO()))
                stack.enter_context(
                    patch.object(
                        entrypoint,
                        "sys",
                        SimpleNamespace(argv=["dts", *arguments], modules={}, exit=sys.exit),
                    )
                )
                stack.enter_context(patch.dict(os.environ, {"DTSHELL_LIB": ""}))
                stack.enter_context(patch("dt_shell.DTShell", return_value=self.shell))
                stack.enter_context(patch("dt_shell.checks.environment.abort_if_running_with_sudo"))
                stack.enter_context(patch("dt_shell.logging.setup_logging_color"))
                for flag in ("DEBUG", "VERBOSE", "QUIET"):
                    stack.enter_context(patch.object(DTShellConstants, flag, getattr(DTShellConstants, flag)))
                if expected_code is None:
                    entrypoint.dts()
                else:
                    with self.assertRaises(SystemExit) as result:
                        entrypoint.dts()
                    self.assertEqual(expected_code, result.exception.code)
                rendered = output.getvalue()
                self.assertIn("Available sub-commands", rendered)
                self.assertEqual(expected_code is not None, "not recognized" in rendered)
                for description in self.shell.profile.command_descriptions["developer"][
                    "subcommands"
                ].values():
                    self.assertIn(description["description"], rendered)

    def test_developer_leaf_help_loads_the_real_command(self):
        for subcommand in ("status", "renew", "clear"):
            with self.subTest(subcommand=subcommand):
                output, _ = self.execute(["developer", subcommand, "--help"], 0)
                self.assertIn(f"usage: dts developer {subcommand}", output)
        self.assertFalse(self.shell._skeleton)

    def test_developer_leaf_commands_reject_extra_arguments(self):
        for subcommand in ("status", "renew", "clear"):
            with self.subTest(subcommand=subcommand):
                _, errors = self.execute(["developer", subcommand, "unexpected"], 2)
                self.assertIn(f"usage: dts developer {subcommand}", errors)
                self.assertIn("unrecognized arguments", errors)

    def test_developer_leaf_commands_forward_only_their_own_subcommand(self):
        manage = Mock()
        native = SimpleNamespace(
            ReleaseIntegrityError=RuntimeError,
            manage_developer_authorization=manage,
            is_developer_mode=lambda: False,
            verify_installation=Mock(),
        )
        with patch("dt_shell.embedded.developer.is_release_build", return_value=True), patch.dict(
            "sys.modules", {"dt_shell_release": native}
        ):
            for subcommand in ("status", "renew", "clear"):
                Python3Environment().execute(self.shell, ["developer", subcommand])
        self.assertEqual([call(["status"]), call(["renew"]), call(["clear"])], manage.call_args_list)

    def test_native_developer_errors_remain_explicit(self):
        native = SimpleNamespace(
            ReleaseIntegrityError=RuntimeError,
            manage_developer_authorization=Mock(side_effect=RuntimeError("Developer grant denied")),
            is_developer_mode=lambda: False,
            verify_installation=Mock(),
        )
        with patch("dt_shell.embedded.developer.is_release_build", return_value=True), patch.dict(
            "sys.modules", {"dt_shell_release": native}
        ):
            output, _ = self.execute(["developer", "renew"], 1)
        self.assertIn("Developer grant denied", output)

    def test_source_developer_operations_explicitly_require_native_dts(self):
        with patch.object(self.shell, "reload_commands", wraps=self.shell.reload_commands) as reload:
            for operation in ("status", "renew", "clear"):
                with self.subTest(operation=operation):
                    output, _ = self.execute(["developer", operation], 1)
                    self.assertIn("official native DTS installation", output)
                    self.assertIn("not an authenticated official runtime", output)
            reload.assert_called_once_with(skeleton=False)

    def test_loaded_commands_do_not_need_a_second_initialization(self):
        self.shell.reload_commands(skeleton=False)
        with patch.object(self.shell, "reload_commands") as reload:
            output, _ = self.execute(["developer", "status", "--help"], 0)
            self.assertIn("usage: dts developer status", output)
            reload.assert_not_called()

    def test_in_process_exit_and_its_alias_execute_the_real_command(self):
        for name in ("exit", "quit"):
            with self.subTest(command=name):
                output, _ = self.execute([name], None)
                self.assertIn("Bye bye!", output)

    def test_command_loading_errors_are_reported_instead_of_ignored(self):
        with patch.object(
            self.shell, "reload_commands", side_effect=CommandsLoadingException("Command import failed")
        ):
            output, _ = self.execute(["developer", "status"], 1)
        self.assertIn("Command import failed", output)


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
