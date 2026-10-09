import dataclasses
import json
import os
import platform
import subprocess
import sys
import venv
from abc import ABCMeta, abstractmethod
from traceback import format_exc
from typing import Optional, List, Dict


from . import logger
from .exceptions import ShellInitException, InvalidEnvironment, CommandsLoadingException, UserError, \
    UserAborted
from .constants import SHELL_REQUIREMENTS_LIST, DTShellConstants
from .database.utils import InstalledDependenciesDatabase
from .integrity import is_release_build, verify_release_integrity
from .logging import dts_print
from .utils import install_pip_tool, pip_install, replace_spaces, print_debug_info, pretty_json


class ShellCommandEnvironmentAbs(metaclass=ABCMeta):

    @abstractmethod
    def execute(self, shell, args: List[str]):
        raise NotImplementedError("Subclasses should implement the function execute()")


def virtualenv_interpreter(venv_dir: str) -> str:
    if sys.platform == "win32":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python3")


def check_release_interpreter(interpreter: str) -> None:
    if not is_release_build():
        return
    code = (
        "import json, platform, sys; "
        "print(json.dumps([sys.implementation.cache_tag, sys.platform, platform.machine().lower()]))"
    )
    try:
        actual = json.loads(subprocess.check_output([interpreter, "-c", code], text=True, timeout=10))
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
        raise ShellInitException(f"Could not check the profile interpreter '{interpreter}': {error}") from error
    expected = [sys.implementation.cache_tag, sys.platform, platform.machine().lower()]
    if actual != expected:
        raise UserError(
            f"The profile interpreter '{interpreter}' is incompatible with this compiled DTS release. "
            f"Expected {expected}; found {actual}. Use a profile virtual environment with the same "
            "Python minor version, operating system, and architecture as the installed DTS package. "
            "Remove DTSHELL_VENV_DIR if it selects an incompatible custom environment."
        )


@dataclasses.dataclass
class Python3Environment(ShellCommandEnvironmentAbs):
    """
    Python3 environment shared with the shell library.
    Default for all the distros up to and including 'daffy'.
    """

    def execute(self, shell, args: List[str]):
        from .shell import DTShell
        from dtproject.exceptions import DTProjectNotFound
        shell: DTShell
        # run shell
        known_exceptions = (InvalidEnvironment, CommandsLoadingException, DTProjectNotFound)
        try:
            args = map(replace_spaces, args)
            cmdline = " ".join(args)
            shell.onecmd(cmdline)
        except UserError as e:
            msg = str(e)
            dts_print(msg, "red")
            print_debug_info()
            sys.exit(1)
        except known_exceptions as e:
            msg = str(e)
            dts_print(msg, "red")
            print_debug_info()
            sys.exit(1)
        except SystemExit:
            raise
        except (UserAborted, KeyboardInterrupt):
            dts_print("User aborted operation.")
            pass
        except BaseException:
            msg = format_exc()
            dts_print(msg, "red", attrs=["bold"])
            print_debug_info()
            sys.exit(2)


@dataclasses.dataclass
class VirtualPython3Environment(ShellCommandEnvironmentAbs):
    """
    Virtual Python3 environment dedicated to a profile and NOT SHARED with the shell library.
    Default for the 'ente' distribution.
    """

    def execute(self, shell, _: List[str]):
        verify_release_integrity()
        from .shell import DTShell
        shell: DTShell
        # ---
        # we make a virtual environment
        DTSHELL_VENV_DIR: str = os.environ.get("DTSHELL_VENV_DIR", None)
        venv_leave_alone: bool = False
        if DTSHELL_VENV_DIR:
            logger.info(
                f"Using virtual environment from '{DTSHELL_VENV_DIR}' as instructed by the environment "
                f"variable DTSHELL_VENV_DIR.")
            venv_dir: str = DTSHELL_VENV_DIR
            venv_leave_alone = True
        else:
            venv_dir: str = os.path.join(shell.profile.path, "venv")

        # define path to virtual env's interpreter
        interpreter_fpath: str = virtualenv_interpreter(venv_dir)

        # make and configure env path if it does not exist
        # TODO: this is a place where a --hard-reset flag would ignore the fact that the venv already exists
        #  and make a new one
        if not os.path.exists(interpreter_fpath):
            if venv_leave_alone:
                msg: str = f"The custom Virtual Environment path '{venv_dir}' was given but no virtual " \
                           f"environments were found at that location."
                logger.error(msg)
                raise ShellInitException(msg)

            # make venv if it does not exist
            logger.info(f"Creating new virtual environment in '{venv_dir}'...")
            os.makedirs(venv_dir, exist_ok=True)
            venv.create(
                venv_dir,
                system_site_packages=False,
                clear=False,
                symlinks=sys.platform != "win32",
                with_pip=False,
                prompt="dts"
            )
            install_pip_tool(interpreter_fpath)

        check_release_interpreter(interpreter_fpath)

        # install dependencies
        cache: InstalledDependenciesDatabase = InstalledDependenciesDatabase.load(shell.profile)
        # - shell
        if DTShellConstants.VERBOSE:
            logger.debug("Checking for changes in the shell's dependencies list...")
        if cache.needs_install_step(SHELL_REQUIREMENTS_LIST):
            # warn user of detected changes (if any)
            if cache.contains(SHELL_REQUIREMENTS_LIST):
                logger.info("Detected changes in the dependencies list for the shell")
            # proceed with installing new dependencies
            logger.info("Installing shell dependencies...")
            pip_install(interpreter_fpath, SHELL_REQUIREMENTS_LIST)
            cache.mark_as_installed(SHELL_REQUIREMENTS_LIST)
        else:
            if DTShellConstants.VERBOSE:
                logger.debug("No new dependencies or constraints detected")
        # - command sets
        for cs in shell.command_sets:
            if DTShellConstants.VERBOSE:
                logger.debug(f"Checking for changes in the dependencies list for command set '{cs.name}'...")
            requirements_list: Optional[str] = cs.configuration.requirements()
            if cache.needs_install_step(requirements_list):
                # warn user of detected changes (if any)
                if cache.contains(requirements_list):
                    logger.info(f"Detected changes in the dependencies list for the command set '{cs.name}'")
                # proceed with installing new dependencies
                logger.info(f"Installing dependencies for command set '{cs.name}'...")
                pip_install(interpreter_fpath, requirements_list)
                cache.mark_as_installed(requirements_list)
            else:
                if DTShellConstants.VERBOSE:
                    logger.debug("No new dependencies or constraints detected")

        # run shell in virtual environment
        if is_release_build():
            import dt_shell_release
            entry = (
                "import importlib.util, sys; "
                f"spec = importlib.util.spec_from_file_location('dt_shell_release', {dt_shell_release.__file__!r}); "
                "module = importlib.util.module_from_spec(spec); "
                "sys.modules['dt_shell_release'] = module; spec.loader.exec_module(module); "
                "module.delegated_main()"
            )
        else:
            entry = (
                "import os, sys; "
                "sys.path.extend(p for p in os.environ['EXTRA_PYTHONPATH'].split(os.pathsep) if p); "
                "from dt_shell_cli.main import main; main()"
            )
        exec_args: List[str] = [interpreter_fpath, interpreter_fpath, "-c", entry, *sys.argv[1:]]

        exec_env: Dict[str, str] = {
            **os.environ,
            "EXTRA_PYTHONPATH": os.pathsep.join(sys.path),
            "IGNORE_ENVIRONMENTS": "1",
        }
        exec_env.pop("PYTHONPATH", None)

        if DTShellConstants.VERBOSE:
            logger.debug(f"Running command: {exec_args}")
            logger.debug(f"Environment: {exec_env}")

        # noinspection PyTypeChecker
        logger.debug(f"Delegating execution to:\n"
                     f"\tCommand: {exec_args}\n"
                     f"\tEnvironment: {pretty_json(exec_env, indent_len=12)}")
        os.execle(*exec_args, exec_env)


@dataclasses.dataclass
class DockerContainerEnvironment(ShellCommandEnvironmentAbs):
    """
    Each command is run inside a separate container.
    Supported since the 'ente' distribution.
    """
    image: str
    configuration: dict = dataclasses.field(default_factory=dict)

    def execute(self, shell, args: List[str]):
        from .shell import DTShell
        shell: DTShell
        # ---
        # TODO: implement this
        raise NotImplementedError("TODO")


DEFAULT_COMMAND_ENVIRONMENT: ShellCommandEnvironmentAbs = Python3Environment()
