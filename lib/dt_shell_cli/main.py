import os
import sys
from typing import Optional

import cython

if cython.compiled:
    from dt_shell_release import verify_installation
    verify_installation()

# add the content of the environment variable EXTRA_PYTHONPATH to the current path
sys.path.extend(path for path in os.environ.get("EXTRA_PYTHONPATH", "").split(os.pathsep) if path)

import logging

from dt_shell_cli import logger

from dt_shell import DTShell, dtslogger, CommandsLoadingException
from dt_shell.shell import get_cli_options
from dt_shell.logging import setup_logging_color, dts_print
from dt_shell.constants import DTShellConstants
from dt_shell.environments import Python3Environment
from dt_shell.checks.environment import abort_if_running_with_sudo
from dt_shell.integrity import verify_release_integrity


# NOTE: this file runs the shell in this interpreter and in quiet mode, the entrypoint should always be
#       the file dts.py.


def main() -> None:
    verify_release_integrity()

    # make sure we are not running as sudo
    abort_if_running_with_sudo()

    # configure logger
    setup_logging_color()

    # parse shell options (anything between `dts` and the first word that does not start with --)
    cli_arguments = sys.argv[1:]
    cli_options, arguments = get_cli_options(cli_arguments)

    # propagate options to the constants
    DTShellConstants.DEBUG = cli_options.debug
    DTShellConstants.VERBOSE = cli_options.verbose
    DTShellConstants.QUIET = cli_options.quiet

    # we run in quiet mode
    logger.setLevel(logging.WARNING)

    # process options here
    if cli_options.debug:
        dtslogger.setLevel(logging.DEBUG)
    if cli_options.verbose:
        logger.setLevel(logging.DEBUG)

    # instantiate shell
    shell: Optional[DTShell] = None
    try:
        shell = DTShell(
            skeleton=False,
            readonly=False,
            banner=False,
            billboard=False,
            profile=cli_options.profile
        )
    except CommandsLoadingException as e:
        dts_print("FATAL: " + str(e))
        exit(90)
    except Exception as e:
        dts_print("FATAL: " + str(e))
        exit(91)

    # run command in this interpreter
    Python3Environment().execute(shell, arguments)


if __name__ == '__main__':
    main()
