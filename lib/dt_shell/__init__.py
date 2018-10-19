# -*- coding: utf-8 -*-
import logging
import sys

from dt_shell.utils import format_exception
from .exceptions import *

logging.basicConfig()

dtslogger = logging.getLogger('dts')
dtslogger.setLevel(logging.DEBUG)

__version__ = '3.0.23'

dtslogger.info('duckietown-shell %s' % __version__)

import termcolor

from .cli import DTShell, dts_print

from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder


def cli_main():
    from .col_logging import setup_logging_color
    setup_logging_color()

    known_exceptions = (InvalidEnvironment,)
    try:
        cli_main_()
    except UserError as e:
        msg = str(e)
        dts_print(msg, 'red')
        sys.exit(1)
    except known_exceptions as e:
        msg = str(e)
        dts_print(msg, 'red')
        sys.exit(1)
    except SystemExit:
        raise
    except BaseException as e:
        msg = format_exception(e)
        dts_print(msg, 'red', attrs=['bold'])
        sys.exit(2)


def cli_main_():
    from .env_checks import abort_if_running_with_sudo
    abort_if_running_with_sudo()
    # Problems with a step in the Duckiebot operation manual?
    #
    #     Report here: https://github.com/duckietown/docs-opmanual_duckiebot/issues

    # TODO: register handler for Ctrl-C
    url = href("https://github.com/duckietown/duckietown-shell-commands/issues")
    msg = """

Problems with a command?

Report here: {url}

Troubleshooting:

- If some commands update fail, delete ~/.dt-shell/commands

- To reset the shell to "factory settings", delete ~/.dt-shell

  (Note: you will have to re-configure.)

    """.format(url=url)
    dts_print(msg)

    from .exceptions import InvalidEnvironment, UserError

    shell = DTShell()
    arguments = sys.argv[1:]

    if arguments:
        from dt_shell.utils import replace_spaces
        arguments = map(replace_spaces, arguments)
        cmdline = " ".join(arguments)
        shell.onecmd(cmdline)
    else:
        shell.cmdloop()


def href(x):
    return termcolor.colored(x, 'blue', attrs=['underline'])
