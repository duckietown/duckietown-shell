import dataclasses
import os
import subprocess
import sys
import venv
from abc import ABCMeta, abstractmethod
from traceback import format_exc
from typing import Optional, List, Dict


from . import logger
from .exceptions import ShellInitException, InvalidEnvironment, CommandsLoadingException, UserError, \
    UserAborted
from .constants import SHELL_LIB_DIR, SHELL_REQUIREMENTS_LIST, DTShellConstants
from .database.utils import InstalledDependenciesDatabase
from .logging import dts_print
from .utils import pip_install, replace_spaces, print_debug_info


class ShellCommandEnvironmentAbs(metaclass=ABCMeta):

    @abstractmethod
    def execute(self, shell, args: List[str]):
        raise NotImplementedError("Subclasses should implement the function execute()")


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
        interpreter_fpath: str = os.path.join(venv_dir, "bin", "python3")

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
                symlinks=True,
                with_pip=False,
                prompt="dts"
            )
            # install pip
            get_pip_fpath: str = os.path.join(SHELL_LIB_DIR, "assets", "get-pip.py")
            assert os.path.exists(get_pip_fpath)
            logger.info(f"Installing pip...")
            try:
                subprocess.check_output([interpreter_fpath, get_pip_fpath], stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                # TODO: test this failure case on purpose
                msg: str = "An error occurred while installing pip in the virtual environment"
                raise ShellInitException(msg, stdout=e.stdout, stderr=e.stderr)

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
        import dt_shell_cli
        main_py: str = os.path.join(os.path.abspath(dt_shell_cli.__path__[0]), "main.py")
        exec_args: List[str] = [interpreter_fpath, interpreter_fpath, main_py, *sys.argv[1:]]

        exec_env: Dict[str, str] = {
            **os.environ,
            "EXTRA_PYTHONPATH": ":".join(sys.path),
            "IGNORE_ENVIRONMENTS": "1",
        }
        exec_env.pop("PYTHONPATH", None)

        if DTShellConstants.VERBOSE:
            logger.debug(f"Running command: {exec_args}")
            logger.debug(f"Environment: {exec_env}")

        # noinspection PyTypeChecker
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
