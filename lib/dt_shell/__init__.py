# -*- coding: utf-8 -*-
import traceback

__version__ = '0.2.17'


from .cli import DTShell


from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder


def cli_main():
    # TODO: register handler for Ctrl-C
    import sys

    arguments = sys.argv[1:]
    shell = DTShell()
    try:
        if arguments:
            cmdline = " ".join(arguments)
            shell.onecmd(cmdline)
        else:
            shell.cmdloop()
    except Exception as e:
        print(traceback.format_exc(e))
        sys.exit(2)
