import sys
import os

# add the content of the environment variable EXTRA_PYTHONPATH to the current path
sys.path.extend(os.environ.get("EXTRA_PYTHONPATH", "").split(":"))

import locale
import logging
from traceback import format_exc

import yaml

import dt_shell
from dt_shell import __version__
from dt_shell.checks.environment import abort_if_running_with_sudo
from dt_shell.checks.packages import _get_installed_distributions
from dt_shell.exceptions import (
    CommandsLoadingException,
    InvalidEnvironment,
    UserError,
)
from dt_shell.logging import dts_print, setup_logging_color
from dt_shell.shell import DTShell, get_cli_options
from dt_shell.utils import replace_spaces, DebugInfo
from dt_shell_cli import logger


def cli_main() -> None:
    setup_logging_color()

    known_exceptions = (InvalidEnvironment, CommandsLoadingException)
    try:
        _cli_main()
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
    except KeyboardInterrupt:
        dts_print("User aborted operation.")
        pass
    except BaseException:
        msg = format_exc()
        dts_print(msg, "red", attrs=["bold"])
        print_debug_info()
        sys.exit(2)


def print_debug_info() -> None:
    v = DebugInfo.name2versions
    v["python"] = sys.version
    v["duckietown-shell"] = __version__


    #TODO: we don't have shell-version anymore
    # try:
    #     shell_config = read_shell_config()
    #     commands_version = shell_config.duckietown_version
    # except:
    #     commands_version = "ND"
    # v["commands-version"] = commands_version

    #TODO: add command set versions

    v["encodings"] = {
        "stdout": sys.stdout.encoding,
        "stderr": sys.stderr.encoding,
        "locale": locale.getpreferredencoding(),
    }

    try:
        installed = _get_installed_distributions()
        pkgs = {_.project_name: _.version for _ in installed}
        for pkg_name, pkg_version in pkgs.items():
            include = (
                ("duckietown" in pkg_name)
                or ("dt-" in pkg_name)
                or ("-z" in pkg_name)
                or ("aido" in pkg_name)
            )
            if include:
                v[pkg_name] = pkg_version
    except ImportError:
        logger.warning('Please update "pip" to have better debug info.')

    versions = yaml.dump(v, default_flow_style=False)
    # Please = termcolor.colored('Please', 'red', attrs=['bold'])
    fn = "~/shell-debug-info.txt"
    fn = os.path.expanduser(fn)
    with open(fn, "w") as f:
        f.write(versions)
    msg = f"""\
To report a bug, please also include the contents of {fn}
"""
    dts_print(msg, "red")


def _cli_main() -> None:
    # make sure we are not running as sudo
    abort_if_running_with_sudo()

    # TODO: register handler for Ctrl-C
    cli_arguments = sys.argv[1:]
    cli_options, arguments = get_cli_options(cli_arguments)

    # process options here
    if cli_options.debug:
        logger.setLevel(logging.DEBUG)


    # TODO: we don't have a shell config object anymore, we use databases instead
    # try:
    #     shell_config = read_shell_config()
    # except ConfigInvalid as e:
    #     msg = "Cannot read the malformed config. Please delete the file."
    #     raise UserError(msg) from e
    # except ConfigNotPresent:
    #     shell_config = get_shell_config_default()
    #     write_shell_config(shell_config)


    # instantiate shell
    shell = DTShell(banner=False)

    # populate singleton
    dt_shell.shell = shell

    # if arguments are given, we run a single command and then we exit, otherwise we enter interactive mode
    if arguments:
        arguments = map(replace_spaces, arguments)
        cmdline = " ".join(arguments)
        shell.onecmd(cmdline)
    else:
        shell.cmdloop()


if __name__ == '__main__':
    cli_main()
