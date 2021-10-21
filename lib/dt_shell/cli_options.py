import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .constants import ALLOWED_BRANCHES

__all__ = ["CLIOptions", "get_cli_options"]


@dataclass
class CLIOptions:
    debug: bool
    set_version: Optional[str]
    quiet: bool


def get_cli_options(args: List[str]) -> Tuple[CLIOptions, List[str]]:
    """Returns cli options plus other arguments for the commands."""
    allowed_branches = [b.split("(")[0] for b in ALLOWED_BRANCHES]

    if args and not args[0].startswith("-"):
        return CLIOptions(debug=False, set_version=None, quiet=False), args
    parser = argparse.ArgumentParser()

    parser.add_argument("--debug", action="store_true", default=False, help="More debug information")
    parser.add_argument("-q", "--quiet", action="store_true", default=False, help="Quiet execution")
    parser.add_argument(
        "--set-version",
        type=str,
        default=None,
        help=f"Set Duckietown version. Use one of {allowed_branches}. Branches from "
        f"https://github.com/duckietown/duckietown-shell-commands of the form '[branch]-*' are also "
        f"supported.",
    )

    parsed, others = parser.parse_known_args(args)

    return CLIOptions(debug=parsed.debug, set_version=parsed.set_version, quiet=parsed.quiet), others
