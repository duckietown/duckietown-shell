# -*- coding: utf-8 -*-
import logging
import traceback

import sys

if sys.version_info >= (3,):
    msg = "duckietown-shell only works on Python 2.7. Python 3 is not supported yet."
    raise ImportError(msg)


logging.basicConfig()

dtslogger = logging.getLogger('dts')
dtslogger.setLevel(logging.INFO)


__version__ = '3.0.3'

dtslogger.info('duckietown-shell %s' % __version__)

msg = """

    Problems with a step in the Duckiebot operation manual?
    
        Report here: https://github.com/duckietown/docs-opmanual_duckiebot/issues
    
    
    Other problems?  
    
        Report here: https://github.com/duckietown/duckietown-shell-commands/issues
        
        Tips:
        
        - NEVER install duckietown-shell using "sudo". Instead use:
            
            pip install --user -U duckietown-shell
            
          Note the switch "--user" to install in ~/.local
        
        - Delete ~/.dt-shell to reset the shell to "factory settings".
          This is useful if some update fails.
          
          (Note: you will have to re-configure)
          
        - Last resort is deleting ~/.local and re-install from scratch.

"""
dtslogger.info(msg)


import termcolor


from .cli import DTShell

from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder

def cli_main():
    # TODO: register handler for Ctrl-C

    from dt_shell.env_checks import InvalidEnvironment

    shell = DTShell()
    arguments = sys.argv[1:]

    known_exceptions = (InvalidEnvironment,)

    try:
        if arguments:
            cmdline = " ".join(arguments)
            shell.onecmd(cmdline)
        else:
            shell.cmdloop()
    except known_exceptions as e:
        msg = str(e)
        termcolor.cprint(msg, 'yellow')
        sys.exit(1)
    except Exception as e:
        msg = traceback.format_exc(e)
        termcolor.cprint(msg, 'red')
        sys.exit(2)
