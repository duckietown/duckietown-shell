import locale
import logging
import os
import re
import sys
from typing import Dict, Union

import yaml

from . import __version__, dtslogger
from .cli import DTShell, get_local_commands_info
from .cli_options import get_cli_options
from .config import get_shell_config_default, read_shell_config, write_shell_config
from .constants import ALLOWED_BRANCHES
from .env_checks import abort_if_running_with_sudo
from .exceptions import (
    CommandsLoadingException,
    ConfigInvalid,
    ConfigNotPresent,
    InvalidEnvironment,
    UserError,
)
from .logging import dts_print
from .utils import format_exception, href, replace_spaces
from .package_version_check import _get_installed_distributions


class OtherVersions:
    name2versions: Dict[str, Union[str, Dict[str, str]]] = {}


def cli_main() -> None:
    from .col_logging import setup_logging_color

    setup_logging_color()

    known_exceptions = (InvalidEnvironment, CommandsLoadingException)
    try:
        cli_main_()
    except UserError as e:

        msg = str(e)
        dts_print(msg, "red")
        print_version_info()
        sys.exit(1)
    except known_exceptions as e:
        msg = str(e)
        dts_print(msg, "red")
        print_version_info()
        sys.exit(1)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        dts_print("User aborted operation.")
        pass
    except BaseException as e:
        msg = format_exception(e)
        dts_print(msg, "red", attrs=["bold"])
        print_version_info()
        sys.exit(2)


def print_version_info() -> None:
    v = OtherVersions.name2versions
    v["python"] = sys.version
    v["duckietown-shell"] = __version__
    try:
        shell_config = read_shell_config()
        commands_version = shell_config.duckietown_version
    except:
        commands_version = "ND"
    v["commands-version"] = commands_version

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
        dtslogger.warning('Please update "pip" to have better debug info.')

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


def print_info_command() -> None:
    url = href("https://github.com/duckietown/duckietown-shell-commands/issues")
    msg = """

    Problems with a command?

    Report here: {url}

    Troubleshooting:

    - If some commands update fail, delete ~/.dt-shell/commands

    - To reset the shell to "factory settings", delete ~/.dt-shell

      (Note: you will have to re-configure.)

        """.format(
        url=url
    )
    dts_print(msg)


def cli_main_() -> None:
    abort_if_running_with_sudo()

    # Problems with a step in the Duckiebot operation manual?
    #
    #     Report here: https://github.com/duckietown/docs-opmanual_duckiebot/issues

    # TODO: register handler for Ctrl-C
    cli_arguments = sys.argv[1:]
    cli_options, arguments = get_cli_options(cli_arguments)

    if not cli_options.quiet:
        print_info_command()

    # process options here
    if cli_options.debug:
        dtslogger.setLevel(logging.DEBUG)

    try:
        shell_config = read_shell_config()
    except ConfigInvalid as e:
        msg = "Cannot read the malformed config. Please delete the file."
        raise UserError(msg) from e
    except ConfigNotPresent:
        shell_config = get_shell_config_default()
        write_shell_config(shell_config)

    v = cli_options.set_version

    def is_allowed_branch(branch):
        allowed_braches_patterns = map(re.compile, ALLOWED_BRANCHES)
        for p in allowed_braches_patterns:
            if p.match(branch):
                return True
        return False

    if v is not None:
        if not is_allowed_branch(v):
            allowed_braches = [b.split("(")[0] for b in ALLOWED_BRANCHES]
            msg = f"Given version {v!r} is not one of {allowed_braches}."
            raise UserError(msg)
        shell_config.duckietown_version = v
        write_shell_config(shell_config)
        # need this so we can use in non-interactive settings
        sys.exit(0)

    if shell_config.duckietown_version is None:
        msg = """You have not specified a Duckietown version. Please use:

        dts --set-version <version>

        where <version> = daffy, master19
        """
        raise UserError(msg)
    if not cli_options.quiet:
        dtslogger.info(f"Commands version: {shell_config.duckietown_version}")
    commands_info = get_local_commands_info()
    # add subdirectory for version
    if not commands_info.leave_alone:
        commands_info.commands_path = os.path.join(
            commands_info.commands_path, shell_config.duckietown_version
        )

    shell = DTShell(shell_config, commands_info)

    if arguments:
        arguments = map(replace_spaces, arguments)
        cmdline = " ".join(arguments)
        shell.onecmd(cmdline)
    else:
        shell.cmdloop()
