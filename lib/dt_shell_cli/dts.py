import os
import subprocess
import sys
import venv
from typing import Optional, List, Dict

from . import logger
from .constants import SHELL_CLI_LIB_DIR, SHELL_REQUIREMENTS_LIST
from .exceptions import ShellInitException
from .utils import InstalledDependenciesDatabase, pip_install
from dt_shell import DTShell


def _use_this_interpreter(location: Optional[str] = None):
    # import shell library
    from .main import cli_main
    # run shell entrypoint
    cli_main()


def _use_virtual_environment(location: Optional[str] = None):
    # load shell skeleton
    shell = DTShell(skeleton=True, billboard=False)

    # if we don't have a profile, we bail
    if shell.profile is None:
        raise RuntimeError("The shell could not load a profile. This should not have happened, please "
                           "contact technical support")
        # TODO: maybe suggest clearing the profile directory?

    # we make a virtual environment
    DTSHELL_VENV_DIR: str = os.environ.get("DTSHELL_VENV_DIR", None)
    if DTSHELL_VENV_DIR:
        logger.info(f"Using virtual environment from '{DTSHELL_VENV_DIR}' as instructed by the environment "
                    f"variable DTSHELL_VENV_DIR.")
        venv_dir: str = DTSHELL_VENV_DIR
    else:
        venv_dir: str = os.path.join(shell.profile.path, "venv")

    # define path to virtual env's interpreter
    interpreter_fpath: str = os.path.join(venv_dir, "bin", "python3")

    # make and configure env path if it does not exist
    # TODO: this is a place where a --hard-reset flag would ignore the fact that the venv already exists and make a new one
    if not os.path.exists(interpreter_fpath):
        os.makedirs(venv_dir, exist_ok=True)
        # make venv if it does not exist
        logger.info(f"Creating new virtual environment in '{venv_dir}'...")
        venv.create(
            venv_dir,
            system_site_packages=False,
            clear=False,
            symlinks=True,
            with_pip=False,
            prompt="dts"
        )
        # install pip
        get_pip_fpath: str = os.path.join(SHELL_CLI_LIB_DIR, "assets", "get-pip.py")
        assert os.path.exists(get_pip_fpath)
        logger.info(f"Installing pip...")
        try:
            subprocess.check_output([interpreter_fpath, get_pip_fpath], stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            msg: str = "An error occurred while installing pip in the virtual environment"
            raise ShellInitException(msg, stdout=e.stdout, stderr=e.stderr)

    # install dependencies
    cache: InstalledDependenciesDatabase = InstalledDependenciesDatabase.load(shell.profile)
    # - shell
    if cache.needs_install_step(SHELL_REQUIREMENTS_LIST):
        logger.info("Installing shell dependencies...")
        pip_install(interpreter_fpath, SHELL_REQUIREMENTS_LIST)
        cache.mark_as_installed(SHELL_REQUIREMENTS_LIST)
    # - command sets
    for cs in shell.command_sets:
        requirements_list: Optional[str] = cs.configuration.requirements()
        if cache.needs_install_step(requirements_list):
            logger.info(f"Installing dependencies for command set '{cs.name}'...")
            pip_install(interpreter_fpath, requirements_list)
            cache.mark_as_installed(requirements_list)

    # run shell in virtual environment
    main_py: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    exec_args: List[str] = [interpreter_fpath, interpreter_fpath, main_py, *sys.argv[1:]]
    exec_env: Dict[str, str] = {
        **os.environ,
        "EXTRA_PYTHONPATH": ":".join(sys.path),
    }
    exec_env.pop("PYTHONPATH", None)

    # noinspection PyTypeChecker
    os.execle(*exec_args, exec_env)


def unix(location: Optional[str] = None):
    _use_virtual_environment(location=location)


def windows(location: Optional[str] = None):
    _use_this_interpreter(location=location)


def main():
    # custom path to dt_shell library can be set using the DTSHELL_LIB environment variable
    DTSHELL_LIB = os.environ.get("DTSHELL_LIB", None)
    if DTSHELL_LIB:
        DTSHELL_LIB = os.path.abspath(DTSHELL_LIB)
        # make sure the duckietown_shell library exists in the given path
        dt_shell_dir = os.path.join(DTSHELL_LIB, "dt_shell")
        if not os.path.exists(dt_shell_dir) or not os.path.isdir(dt_shell_dir):
            logger.fatal("Duckietown Shell library not found in the given DTSHELL_LIB path. "
                         f"Directory '{dt_shell_dir}' does not exist.\n")
            sys.exit(1)
        # make sure the duckietown_shell library is a Python package
        dt_shell_init = os.path.join(DTSHELL_LIB, "dt_shell", "__init__.py")
        if not os.path.exists(dt_shell_init) or not os.path.isfile(dt_shell_init):
            logger.fatal(f"The given directory '{dt_shell_dir}' is not a Python package.\n")
            sys.exit(2)
        # notify user of their choice
        logger.info(f"Using duckietown-shell library from '{DTSHELL_LIB}' as instructed by the environment "
                    f"variable DTSHELL_LIB.")
        # give the given path the highest priority
        sys.path.insert(0, DTSHELL_LIB)

    try:
        # TODO: this is wrong, the environment is not chosen solely based on OS but the command/commandset choose it
        # call system-specific main function
        if sys.platform.startswith('linux'):
            unix(location=DTSHELL_LIB)
        elif sys.platform.startswith('darwin'):
            unix(location=DTSHELL_LIB)
        elif sys.platform.startswith('win32'):
            windows(location=DTSHELL_LIB)
    except ShellInitException as e:
        from dt_shell.logging import dts_print
        from dt_shell_cli.main import print_debug_info
        # ---
        msg = str(e)
        print_debug_info()
        dts_print(msg, "red")
        sys.exit(1)
