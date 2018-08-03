# -*- coding: utf-8 -*-
__version__ = '0.2.0'


from .cli import DTShell


from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder


def cli_main():
    # TODO: register handler for Ctrl-C
    import sys

    arguments = sys.argv[1:]
    shell = DTShell()
    if arguments:
        cmdline = " ".join(arguments)
        shell.onecmd(cmdline)
    else:
        shell.cmdloop()
