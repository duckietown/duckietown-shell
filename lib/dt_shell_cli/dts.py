import logging
import os
import sys
from typing import Optional, Dict, List

# NOTE: DO NOT IMPORT DT_SHELL HERE

from . import logger


# noinspection PyPep8Naming
def dts():
    # make sure we have not imported dt_shell yet
    modules = [m.__name__ for m in sys.modules.values() if m]
    if "dt_shell" in modules:
        logger.fatal("The module 'dt_shell' was found imported before we had a chance to update "
                     "the PYTHONPATH. This should not have happened. Please, contact technical support.")
        return

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
        # give the given path the highest priority
        sys.path.insert(0, DTSHELL_LIB)

    # import dt_shell
    import dt_shell
    from dt_shell.constants import DTShellConstants
    from dt_shell.logging import setup_logging_color, dts_print
    from dt_shell.checks.environment import abort_if_running_with_sudo
    from dt_shell.shell import get_cli_options
    from dt_shell.commands import CommandDescriptor
    from dt_shell.environments import ShellCommandEnvironmentAbs
    from dt_shell.exceptions import CommandNotFound, ShellInitException, UserAborted, UserError, ConfigInvalid
    from dt_shell.utils import replace_spaces, print_debug_info
    from dt_shell import DTShell, dtslogger

    # parse shell options (anything between `dts` and the first word that does not start with --)
    cli_arguments = sys.argv[1:]
    cli_options, arguments = get_cli_options(cli_arguments)

    # perform complete
    if cli_options.complete:
        # disable loggers
        # NOTE: comment these two lines if you want to test what happens when --complete is run. You might
        #       discover that some things that should not happen in readonly mode do indeed happen.
        #       See DTSW-4277 for an example.
        dtslogger.setLevel(logging.CRITICAL + 1)
        logger.setLevel(logging.CRITICAL + 1)
        # ---
        complete()
        exit()

    # propagate options to the constants
    DTShellConstants.DEBUG = cli_options.debug
    DTShellConstants.VERBOSE = cli_options.verbose
    DTShellConstants.QUIET = cli_options.quiet

    # notify user of their choices
    if DTSHELL_LIB:
        logger.info(f"Using duckietown-shell library from '{DTSHELL_LIB}' as instructed by the environment "
                    f"variable DTSHELL_LIB.")
    if DTShellConstants.VERBOSE:
        logger.info(f"Using duckietown-shell library from '{dt_shell.__file__}'")

    # make sure we are not running as sudo
    abort_if_running_with_sudo()

    # configure logger
    setup_logging_color()

    # process options here
    if DTShellConstants.DEBUG:
        dtslogger.setLevel(logging.DEBUG)
    if DTShellConstants.VERBOSE:
        logger.setLevel(logging.DEBUG)

    # load shell skeleton
    try:
        shell = DTShell(
            skeleton=True,
            readonly=False,
            banner=True,
            billboard=True,
            profile=cli_options.profile
        )
    except ConfigInvalid as e:
        dts_print(f"A configuration file or field is invalid.\nDetails:\n\t{str(e)}", "red")
        exit(1)
    except (UserAborted, KeyboardInterrupt):
        dts_print("User aborted operation.")
        return
    except UserError as e:
        msg = str(e)
        dts_print(msg, "red")
        print_debug_info()
        sys.exit(1)

    # if we don't have a profile, we bail
    if shell.profile is None:
        raise RuntimeError("The shell could not load a profile. This should not have happened, please "
                           "contact technical support")
        # TODO: maybe suggest clearing the profile directory?

    # get command's environment and use it to execute the command
    arguments = list(map(replace_spaces, arguments))
    cmdline = " ".join(arguments)
    command: Optional[CommandDescriptor] = None
    try:
        command = shell.get_command(cmdline)
    except CommandNotFound as e:
        inpt: str = cmdline.strip()
        if e.last_matched is None:
            if len(inpt) <= 0:
                # no input, but we only complain if the experience was not interactive
                if shell.performed_migrations or shell.configured_shell or shell.configured_profile:
                    exit(0)
                # no input
                # TODO: maybe suggest possible commands?
                dts_print("Use the syntax\n\n"
                          "\t\tdts [options] command [subcommand1 [subcommand2] ...] [arguments]\n",
                          color="red")
                exit(1)
            else:
                # input was given but it was not recognized
                shell.default(cmdline)

        else:
            # we have a partial match of the arguments
            word: Optional[str] = e.remaining[0] if e.remaining else None
            subcommands: Dict[str] = e.last_matched.commands
            if len(subcommands) > 0:
                subcommands_list: str = "\n\t\t".join(subcommands.keys())
                # the partially matched command has subcommands
                if word:
                    dts_print(
                        f"Sub-command '{word}' not recognized.\n"
                        f"Available sub-commands are:\n\n\t\t{subcommands_list}"
                    )
                else:
                    dts_print(f"Available sub-commands are:\n\n\t\t{subcommands_list}")
            else:
                # the partially matched command is a leaf command (i.e., no subcommands)
                # TODO: make sure this does not happen
                raise NotImplementedError("NOT IMPLEMENTED")

    if command is not None:
        env: ShellCommandEnvironmentAbs = command.environment
        logger.debug(f"Running command '{command.selector}' in environment '{env.__class__.__name__}'")
        try:
            env.execute(shell, arguments)
        except ShellInitException:
            logger.error("An error occurred, the reason for the error should be printed above.")
            exit(99)


def complete():
    """
    NOTE: If you want to test the autocomplete output, use the following command:
        .
            dts --complete <idx> dts <word1> <word2> ...
        .
        where <idx> is the index corresponding to the word we want to complete.
        For example, pressing <Tab> on the partial command "dts devel bu" would generate the
        command
        .
            dts --complete 2 dts devel bu
        .
        which, if run, would print the string "bump build" for BASH to break at the space.
    """
    from dt_shell import DTShell

    try:
        shell = DTShell(
            skeleton=True,
            readonly=True,
            banner=False,
            billboard=False
        )
    except:
        exit()

    def do_complete(comp_cword: str, *comp_words: str):
        comp_cword: int = int(comp_cword)
        comp_words: List[str] = list(comp_words)
        # add empty word if the pointer is past the last word (we are list all possible next words)
        if comp_cword == len(comp_words):
            comp_words.append("")
        # ---
        comp_line: str = " ".join(comp_words[1:])
        comp_word: str = comp_words[comp_cword]
        root_cmd: str = comp_words[1]
        if root_cmd in shell.commands:
            complete_fcn = getattr(shell, f"complete_{root_cmd}")
            return complete_fcn(comp_word, comp_line, 0, 0)
        else:
            items = shell.commands.keys()
            return (item for item in items if item.startswith(comp_word))

    suggestions: List[str] = do_complete(*sys.argv[2:])
    if suggestions:
        sys.stdout.write(" ".join(suggestions))
        sys.stdout.flush()
    exit(0)


if __name__ == '__main__':
    dts()
