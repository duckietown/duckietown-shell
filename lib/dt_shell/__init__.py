# -*- coding: utf-8 -*-
import logging
import sys
import traceback

import six

from .exceptions import *

logging.basicConfig()

dtslogger = logging.getLogger('dts')
dtslogger.setLevel(logging.DEBUG)

__version__ = '3.0.18'

dtslogger.info('duckietown-shell %s' % __version__)

import termcolor


from .cli import DTShell, dts_print

from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder


if sys.version_info >= (3,):
    msg = "duckietown-shell only works on Python 2.7. Python 3 is not supported yet."
    dtslogger.warning(msg)
    # raise ImportError(msg)


def cli_main():
    from .col_logging import setup_logging_color
    setup_logging_color()
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

    known_exceptions = (InvalidEnvironment,)

    try:
        if arguments:
            from dt_shell.utils import replace_spaces
            arguments = map(replace_spaces, arguments)
            cmdline = " ".join(arguments)
            shell.onecmd(cmdline)
        else:
            shell.cmdloop()
    except UserError as e:
        msg = str(e)
        termcolor.cprint(msg, 'red')
        sys.exit(1)
    except known_exceptions as e:
        msg = str(e)
        termcolor.cprint(msg, 'yellow')
        sys.exit(1)
    except Exception as e:
        if six.PY2:
            msg = traceback.format_exc(e)
        else:
            msg = traceback.format_exc(None, e)
        termcolor.cprint(msg, 'red')
        sys.exit(2)


def href(x):
    return termcolor.colored(x, 'blue', attrs=['underline'])
