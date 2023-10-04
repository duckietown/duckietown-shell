import os
import sys


# add the content of the environment variable EXTRA_PYTHONPATH to the current path
sys.path.extend(os.environ.get("EXTRA_PYTHONPATH", "").split(":"))

import logging

from dt_shell_cli import logger

import dt_shell
from dt_shell import DTShell, dtslogger
from dt_shell.shell import get_cli_options
from dt_shell.logging import setup_logging_color
from dt_shell.constants import DTShellConstants
from dt_shell.environments import Python3Environment
from dt_shell.checks.environment import abort_if_running_with_sudo


def main() -> None:
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

    # process options here
    if cli_options.debug:
        dtslogger.setLevel(logging.DEBUG)
    if cli_options.verbose:
        logger.setLevel(logging.DEBUG)

    # instantiate shell
    shell = DTShell(
        skeleton=False,
        readonly=False,
        banner=False,
        billboard=False,
    )

    # populate singleton
    dt_shell.shell = shell

    # run command in this interpreter
    Python3Environment().execute(shell, arguments)


if __name__ == '__main__':
    main()
