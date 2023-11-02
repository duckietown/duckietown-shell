import locale
import os.path
import sys

import yaml

from dt_shell.checks.packages import _get_installed_distributions
from dt_shell.logging import dts_print
from dt_shell.utils import DebugInfo

from dt_shell import __version__
from dt_shell_cli import logger


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
    msg = f"To report a bug, please also include the contents of {fn}"
    dts_print(msg, "yellow")
